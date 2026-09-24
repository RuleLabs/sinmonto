"""Benchmark rc4 — python3 scripts/benchmark.py (depuis la racine du dépôt).

Écrit par Grok (audit adversarial + benchmark rc4, 2026-09), adapté ici
uniquement pour des chemins portables (racine du dépôt déduite du fichier
plutôt qu'un chemin absolu de sandbox). Logique de mesure inchangée. Les
chiffres de docs/benchmark-rc4.md viennent d'une exécution de CE script
sur le rc4 corrigé (après les 4 bugs + le fix deque trouvés en revue
adversariale) — pas de la première exécution pré-correctifs.
"""

from __future__ import annotations

import gc
import json
import os
import platform
import statistics
import sys
import time
import tracemalloc
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sinmonto import (  # noqa: E402
    DecisionEngine,
    Effect,
    Fact,
    Field,
    InMemoryFactStore,
    Rule,
    Signal,
)

D0 = Decimal('0')


def uid(i: int) -> uuid.UUID:
    return uuid.UUID(int=i + 1)


def make_signal(i: int = 0, *, entity: str = 'bench', payload: dict | None = None, fact_type: str = 'transaction') -> Signal:
    f = Fact(uid(i * 2), entity, fact_type, payload or {'amount': 150}, D0)
    return Signal(uid(i * 2 + 1), f, fact_type, D0)


def stats_ns(samples: list[int]) -> dict[str, float]:
    s = sorted(samples)
    def pct(p: float) -> float:
        idx = min(len(s) - 1, max(0, int(round((p / 100) * (len(s) - 1)))))
        return s[idx] / 1e3
    return {
        'n': len(samples),
        'median_us': statistics.median(samples) / 1e3,
        'p95_us': pct(95),
        'p99_us': pct(99),
        'mean_us': statistics.mean(samples) / 1e3,
        'min_us': min(samples) / 1e3,
        'max_us': max(samples) / 1e3,
    }


def bench_loop(fn: Callable[[int], object], *, warmup: int, n: int) -> dict:
    for i in range(warmup):
        fn(i)
    gc.collect()
    samples: list[int] = []
    t0 = time.perf_counter_ns()
    for i in range(n):
        a = time.perf_counter_ns()
        fn(i)
        samples.append(time.perf_counter_ns() - a)
    total = time.perf_counter_ns() - t0
    st = stats_ns(samples)
    st['throughput_ops_s'] = n / (total / 1e9)
    return st


def engine_rules(n: int, *, indexed: bool = False, action: str = 'none') -> DecisionEngine:
    e = DecisionEngine()
    for i in range(n):
        field = f'f{i}' if indexed else 'amount'
        cond = Field(field) >= 0
        if action == 'effect':
            act = (lambda rid: lambda ctx, fact: Effect('ok', {'r': rid}, rid))(f'r{i}')
        elif action == 'context':
            act = lambda ctx, fact: {'counter': ctx.get('counter', 0) + 1}
        else:
            act = None
        e.add_rule(Rule(f'r{i}', priority=n-i, condition=cond, action=act))
    e.compile()
    return e


def run_eval_suite() -> list[dict]:
    out = []
    for n_rules in [1, 10, 50, 100, 500, 1000]:
        e = engine_rules(n_rules, indexed=False)
        s = make_signal(42)
        out.append({'suite':'eval_all_candidates','rules':n_rules,
                    **bench_loop(lambda i: e.evaluate(s), warmup=20, n=max(100, 50000//n_rules))})
        e2 = engine_rules(n_rules, indexed=True)
        s2 = make_signal(42, payload={'f0': 1})
        out.append({'suite':'eval_selective_index','rules':n_rules,
                    **bench_loop(lambda i: e2.evaluate(s2), warmup=20, n=max(100, 50000//n_rules))})
    return out


def run_action_suite() -> list[dict]:
    out = []
    for action in ['none', 'effect', 'context']:
        e = engine_rules(20, indexed=False, action=action)
        s = make_signal(100, payload={'amount': 150})
        out.append({'suite':f'action_{action}','rules':20,
                    **bench_loop(lambda i: e.evaluate(s), warmup=20, n=500)})
    return out


def make_cascade_engine(target_depth: int, *, branch: int = 1) -> DecisionEngine:
    e = DecisionEngine()
    e._config['max_derived_depth'] = max(target_depth + 2, 3)
    def act(ctx, fact):
        stage = int(fact.payload.get('stage', 0))
        if stage >= target_depth:
            return None
        children = []
        for b in range(branch):
            child_fact = Fact(
                uid(1_000_000 + stage * 10_000 + b),
                fact.entity_id,
                'cascade',
                {'stage': stage + 1, 'branch': b},
                D0,
            )
            children.append(Signal(
                uid(2_000_000 + stage * 10_000 + b), child_fact, 'derived', D0
            ))
        return children[0] if branch == 1 else children
    e.add_rule(Rule('cascade', priority=1, condition=None, action=act))
    e.compile()
    return e


def run_cascade_suite() -> list[dict]:
    out = []
    for depth in [0, 1, 2, 3, 5, 8, 10]:
        e = make_cascade_engine(depth, branch=1)
        root = Signal(uid(9_000_000+depth*2), Fact(uid(9_100_000+depth), 'bench', 'cascade', {'stage':0}, D0), 'root', D0)
        d = e.evaluate(root)
        hops = {t.hop for t in d.trace.rule_traces}
        out.append({'suite':'cascade_linear','target_depth':depth,'rule_traces':len(d.trace.rule_traces),
                    'hops':len(hops),'context_version':d.context_version,
                    **bench_loop(lambda i: e.evaluate(root), warmup=5, n=100)})
    return out


def run_branch_suite() -> list[dict]:
    out = []
    for depth, branch in [(3,2),(4,2),(5,2),(6,2),(4,3)]:
        e = make_cascade_engine(depth, branch=branch)
        root = Signal(uid(3_000_000+depth*100+branch), Fact(uid(3_100_000+depth*100+branch), 'bench', 'cascade', {'stage':0}, D0), 'root', D0)
        d = e.evaluate(root)
        out.append({'suite':'cascade_branching','depth':depth,'branch':branch,
                    'rule_traces':len(d.trace.rule_traces),
                    **bench_loop(lambda i: e.evaluate(root), warmup=2, n=30)})
    return out


def run_error_suite() -> list[dict]:
    out = []
    for policy in ['continue', 'fail_fast', 'fail_loud']:
        e = DecisionEngine()
        e._config['rule_error_policy'] = policy
        def crash(ctx, fact):
            raise ValueError('bench')
        e.add_rule(Rule('crash', condition=None, action=crash))
        e.compile()
        s = make_signal(555)
        if policy == 'fail_loud':
            def call(i):
                try: e.evaluate(s)
                except Exception: pass
        else:
            def call(i): e.evaluate(s)
        out.append({'suite':'error_policy','policy':policy,
                    **bench_loop(call, warmup=10, n=150)})
    return out


def run_compile_suite() -> list[dict]:
    out = []
    for n in [1, 10, 100, 1000, 5000]:
        samples=[]
        for _ in range(10):
            e=DecisionEngine()
            a=time.perf_counter_ns()
            for i in range(n):
                e.add_rule(Rule(f'r{i}', priority=i, condition=Field('amount') >= i))
            e.compile()
            samples.append(time.perf_counter_ns()-a)
        out.append({'suite':'compile','rules':n, **stats_ns(samples)})
    return out


def run_factstore_query_suite() -> list[dict]:
    out=[]
    for size in [1000, 5000, 10000, 50000, 100000]:
        store=InMemoryFactStore(max_facts=max(size, 1))
        # target entity appears sparsely, so the scan cost is visible.
        for i in range(size):
            ent='target' if i % 1000 == 0 else f'e{i}'
            store.append(Fact(uid(20_000_000+i), ent, 't', {'x':i}, D0))
        def q(i): return store.query('target')
        out.append({'suite':'factstore_query','stored':size,'matches':len(store.query('target')),
                    **bench_loop(q, warmup=3, n=30)})
    return out


def run_memory_suite() -> list[dict]:
    out=[]
    for n in [500, 1000, 2000]:
        gc.collect(); tracemalloc.start()
        before=tracemalloc.take_snapshot()
        e=engine_rules(50, indexed=False)
        for i in range(n):
            e.evaluate(make_signal(i, entity=f'e{i}', payload={'amount':150}))
        after=tracemalloc.take_snapshot()
        current, peak = tracemalloc.get_traced_memory()
        diff=sum(stat.size_diff for stat in after.compare_to(before, 'filename'))
        tracemalloc.stop()
        out.append({'suite':'memory_after_evaluations','evaluations':n,'tracemalloc_current_bytes':current,
                    'tracemalloc_peak_bytes':peak,'snapshot_diff_bytes':diff})
    return out


def run_handcoded_baseline() -> list[dict]:
    out=[]
    for n in [1,10,50,100,500,1000]:
        rules=[(f'f{i}' if False else 'amount', i) for i in range(n)]
        payload={'amount':150}
        def baseline(i):
            x=payload['amount']
            matched=0
            for field, ref in rules:
                if x >= ref:
                    matched += 1
            return matched
        e=engine_rules(n, indexed=False)
        s=make_signal(999+n, payload=payload)
        b=bench_loop(baseline, warmup=20, n=max(100, 50000//n))
        sm=bench_loop(lambda i:e.evaluate(s), warmup=20, n=max(100, 50000//n))
        out.append({'suite':'handcoded_vs_sinmonto','rules':n,'baseline_median_us':b['median_us'],
                    'sinmonto_median_us':sm['median_us'],'overhead_x':sm['median_us']/b['median_us']})
    return out


def main():
    env={
        'python':platform.python_version(),
        'implementation':platform.python_implementation(),
        'platform':platform.platform(),
        'cpu_count':os.cpu_count(),
        'sinmonto_source':str(ROOT),
    }
    # Exact source version from package and git state.
    import sinmonto
    env['sinmonto_version']=sinmonto.__version__
    try:
        import subprocess
        env['git_head']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        env['git_status']=subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True).strip().splitlines()
    except Exception: pass
    results=[]
    for fn in [run_compile_suite, run_eval_suite, run_action_suite, run_cascade_suite,
               run_branch_suite, run_error_suite, run_factstore_query_suite, run_handcoded_baseline,
               run_memory_suite]:
        results.extend(fn())
    data={'environment':env,'results':results}
    out = ROOT / 'benchmark_results.json'
    out.write_text(json.dumps(data,indent=2,ensure_ascii=False))
    print(json.dumps(data,indent=2,ensure_ascii=False))

if __name__=='__main__':
    main()

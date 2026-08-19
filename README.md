# sinmonto

*[Version française](./docs/fr/README.md)*

[![tests](https://github.com/RuleLabs/sinmonto/actions/workflows/tests.yml/badge.svg)](https://github.com/RuleLabs/sinmonto/actions/workflows/tests.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](pyproject.toml)

Explainable, deterministic event-driven decision engine, in pure Python — zero dependencies.

From the Fon *Sɛ́n mɔto* ("rule engine"). Every decision carries its own proof: why a rule matched, why another didn't, in what order, with what actual values at the time of evaluation.

**Status: `0.1.0rc3` — technical preview.** The core is tested (42 tests in `tests/` + end-to-end integration) and the silent bugs found in multi-AI cross-review are fixed (see "Known limitations" below for what's deliberately left open). Staying in pre-release until a first round of real external usage feedback — the 0.x API isn't locked yet.

## Why

- **Zero dependencies** — installs and audits anywhere, no dependency tree for a security team to sign off on.
- **Native explainability** — every decision produces a complete trace tree, not a log bolted on afterward.
- **Effects-as-data** — a rule never makes a network call or a database write. It describes an `Effect`. A separate executor applies it. This makes the engine testable and replayable by construction.
- **Per-entity persistent state** — a `ContextStore` keeps an entity's memory (user, device, transaction) from one event to the next, without which no running count or cumulative score is possible.
- **Deterministic** — same inputs, same rule-registration order ⇒ same output, bit for bit, including on priority ties. *(Explicit exception: `DecisionTrace.trace_id`, a UUID generated on every evaluation, not reproducible by construction — the guarantee covers matched rules, effects, evaluation order, and context state, not generated identifiers.)*

## Installation

```bash
pip install sinmonto
```

*(Since the version is a pre-release (`0.1.0rc3`), a plain `pip install sinmonto` won't pick it up once published on PyPI — you'll need `pip install --pre sinmonto`, consistent with the preview status above. Until then: `pip install -e .` from a local copy of the repo.)*

## Example

```python
from decimal import Decimal
from uuid import uuid4

from sinmonto import DecisionEngine, Effect, Fact, Field, Signal, rule

engine = DecisionEngine()

@rule(name="high_amount_alert", priority=100,
      condition=(Field("amount") > 1000) & (Field("vip") == False),
      engine=engine)
def check_high_amount(ctx, fact):
    return Effect("FLAG_TRANSACTION", {"reason": "high_amount_non_vip"}, "high_amount_alert")

engine.compile()

fact = Fact(fact_id=uuid4(), entity_id="usr_99", fact_type="payment",
            _payload={"amount": 2500, "vip": False}, timestamp=Decimal("0"))
signal = Signal(signal_id=uuid4(), fact=fact, signal_type="payment_received", timestamp=Decimal("0"))

decision = engine.evaluate(signal)

print(decision.effects)
# (Effect(effect_type='FLAG_TRANSACTION', payload={'reason': 'high_amount_non_vip'}, rule_id='high_amount_alert'),)

trace = decision.trace.rule_traces[0]
print(trace.condition_tree.description, "->", trace.condition_tree.result)
# amount gt 1000 -> True
```

A second signal for `usr_99` automatically picks up the context from the first — see [`examples/end_to_end.py`](./examples/end_to_end.py) and `ContextStore`.

## Cross-review status (2026-08)

The repo went through a multi-AI code cross-review (ChatGPT, Grok, DeepSeek, Kimi, Qwen, Meta AI). Six silent bugs — the ones that betrayed the explainability/determinism promise rather than simple documented gaps — were fixed before this preview: deep-copied context, real rule atomicity (snapshot/restore, including direct `ctx` mutation), `Signal.entity_id`/condition-operator/action-return validation, defensive payload copying, chained `causality`. A second pass (rc2 → rc3), on the actual repo this time rather than a zip, fixed three additional points: deep (not just shallow) copying on `Fact.payload`/`Effect.payload`, clarifying that bit-for-bit determinism excludes `trace_id`, and a packaging issue on `CLAUDE.md`. Full bug-by-bug detail: [`journal-integration.md`](./docs/journal-integration.md) *(French)*.

## Known limitations (v0.1.0-preview) — assumed, not bugs

- Derived signals (`EvaluationResult.derived_signals`) are accepted by the API but **not processed** — no rule cascading in this version. The architecture decision (separate queue? recursive?) is deferred to a dedicated round rather than rushed. Planned for v0.2.0.
- `RuleTrace.duration_ms` is always `Decimal("0")` — no real execution-time measurement yet.
- Nested AND chains aren't flattened in the trace — cosmetic, the logic and short-circuiting remain correct.
- No retention policy on `InMemoryContextStore`/`InMemoryFactStore` — in-memory stores meant for tests/demos/prototypes, not long-running production without a dedicated adapter.
- No time windows, state transitions (FSM), or `engine.replay()` yet — see [`roadmap-vision.md`](./docs/roadmap-vision.md) *(French)*.
- `Fact.payload`/`Effect.payload`/`FrozenContext.values` are protected by deep copy at construction (an external mutation no longer affects them) and read-only `MappingProxyType` at the top level — but `MappingProxyType` only protects that top level: mutating a nested value *through* the proxy (`obj.payload["nested"]["x"] = ...`) is still possible. Not a security hole (an external caller can no longer do anything from their own reference), but not a recursive deep-freeze either.

## Using sinmonto with the help of an AI

[`UTILISATION.md`](./UTILISATION.md) *(French)* — a contributor who *uses* sinmonto (rather than modifying its core) should start there, human or AI. It avoids guessing the API — a real problem: several AIs without repo access invented plausible but fictional class names while working on this project. To contribute to the core itself, see [`CONTRIBUTING.md`](./CONTRIBUTING.md) and [`AGENTS.md`](./AGENTS.md) instead.

## Architecture and governance

This project is built with strict documentation discipline, in cross-review with several AIs. Currently French-only — these are process documents, not usage documentation:

- [`constitution-finale.md`](./docs/constitution-finale.md) — locked architectural principles, stable across every version.
- [`constitution-noyau.md`](./docs/constitution-noyau.md) — full technical specification of what the core builds.
- [`journal-integration.md`](./docs/journal-integration.md) — honest history: what was tried, the bugs found, how they were fixed.
- [`roadmap-vision.md`](./docs/roadmap-vision.md) — what isn't built yet, and why now isn't the time.

## License

Apache License 2.0 — see [`LICENSE`](./LICENSE).

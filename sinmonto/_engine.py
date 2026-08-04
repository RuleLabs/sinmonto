"""AlphaIndex (indexation des règles), DecisionEngine (add_rule, compile,
evaluate) — le cycle complet en 10 étapes (constitution-noyau.md §10).

Historique des corrections d'intégration (voir journal-integration.md pour le
détail complet — problème trouvé, comment, comment corrigé) :

- Rule unifiée avec _dsl.py (un seul Rule, pas deux implémentations qui ne
  s'accordaient pas).
- ctx.commit() corrigé pour matcher la signature réelle de _context.py.
- ConditionTrace réelle utilisée au lieu d'une trace plate synthétique.
- Persistance du contexte entre évaluations (ContextStore) — sans ça, deux
  signaux pour la même entité repartaient d'un contexte vierge à chaque fois.
- Tie-breaking déterministe : AlphaIndex.match() retourne un set, dont
  l'ordre d'itération n'est pas garanti (hash randomization) — la liste de
  candidats est reconstruite dans l'ordre de self._rule_order (déjà une
  liste ordonnée par insertion) avant le tri par priorité, pour que le tri
  stable préserve vraiment l'ordre d'insertion en cas d'égalité (Q4).
- entity_id vient de signal.entity_id, plus d'un "global" arbitraire pour
  les signaux sans fact (timers) — Signal l'exige maintenant explicitement.
- add_rule() valide le type de la condition et lève InvalidConditionError
  au lieu de laisser fuir une AttributeError brute plus tard.

Test sur téléphone : `python3 -m sinmonto._engine` depuis le dossier
parent de sinmonto/.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from ._core import Clock, Decision, Effect, Fact, ManualClock, Signal
from ._context import (
    ContextStore,
    EvaluationContext,
    FactStore,
    InMemoryContextStore,
    InMemoryFactStore,
)
from ._dsl import CompositeCondition, FieldCondition, Rule
from ._trace import ConditionTrace, DecisionTrace, RuleTrace
from ._exceptions import (
    DuplicateRuleError,
    EngineAlreadyCompiledError,
    EngineNotCompiledError,
    InvalidConditionError,
    RuleEvaluationError,
)

_NO_CONDITION_TRACE = ConditionTrace(
    kind="none", description="(pas de condition — toujours vraie)", result=True
)


class AlphaIndex:
    """Palier v1.0 (§4) : indexation par nom de champ référencé uniquement —
    un sur-ensemble de candidates, jamais le match final. Le contrat de
    match() reste "retourne un ensemble", pas un ordre — c'est à l'appelant
    (DecisionEngine.evaluate) de reconstruire un ordre déterministe si besoin,
    pas à l'index de le garantir."""

    def __init__(self) -> None:
        self._field_index: dict[str, set[str]] = {}
        self._unindexed: set[str] = set()
        self._optimized: bool = False

    @staticmethod
    def _extract_fields(condition: "FieldCondition | CompositeCondition") -> set[str]:
        if isinstance(condition, FieldCondition):
            return {condition.field_name}
        fields: set[str] = set()
        for child in condition.children:
            fields |= AlphaIndex._extract_fields(child)
        return fields

    def index_rule(self, rule_id: str, condition: "FieldCondition | CompositeCondition | None") -> None:
        if condition is None:
            self._unindexed.add(rule_id)
            return
        fields = self._extract_fields(condition)
        if not fields:
            self._unindexed.add(rule_id)
            return
        for field_name in fields:
            self._field_index.setdefault(field_name, set()).add(rule_id)

    def match(self, fact: Fact) -> set[str]:
        candidates: set[str] = set(self._unindexed)
        for field_name in fact.payload:
            if field_name in self._field_index:
                candidates |= self._field_index[field_name]
        return candidates

    def optimize(self) -> None:
        """Palier v1.0 : rien à faire. Trier par sélectivité viendra en v1.1+."""
        self._optimized = True


class DecisionEngine:
    def __init__(
        self,
        clock: Clock | None = None,
        fact_store: FactStore | None = None,
        context_store: ContextStore | None = None,
    ) -> None:
        self._clock: Clock = clock if clock is not None else ManualClock()
        self._fact_store: FactStore = fact_store if fact_store is not None else InMemoryFactStore()
        self._context_store: ContextStore = (
            context_store if context_store is not None else InMemoryContextStore()
        )
        self._rules: dict[str, Rule] = {}
        self._rule_order: list[str] = []
        self._compiled: bool = False
        self._alpha_index = AlphaIndex()
        self._config: dict[str, Any] = {
            "rule_error_policy": "continue",  # "continue" | "fail_fast" | "fail_loud"
            "max_derived_depth": 3,
        }

    def add_rule(self, rule: Rule) -> None:
        self._ensure_not_compiled()
        if rule.rule_id in self._rules:
            raise DuplicateRuleError(f"rule_id déjà enregistré : {rule.rule_id}")
        if rule.condition is not None and not isinstance(
            rule.condition, (FieldCondition, CompositeCondition)
        ):
            raise InvalidConditionError(
                f"condition de la règle '{rule.rule_id}' doit être None, "
                f"FieldCondition ou CompositeCondition — reçu "
                f"{type(rule.condition).__name__}"
            )
        self._rules[rule.rule_id] = rule
        self._rule_order.append(rule.rule_id)
        self._alpha_index.index_rule(rule.rule_id, rule.condition)

    def compile(self) -> None:
        self._ensure_not_compiled()
        self._alpha_index.optimize()
        self._compiled = True

    def evaluate(self, signal: Signal) -> Decision:
        self._ensure_compiled()

        fact = signal.fact
        if fact is not None:
            self._fact_store.append(fact)

        entity_id = signal.entity_id

        # Persistance du contexte : reprend le dernier FrozenContext connu de
        # cette entité, plutôt que de repartir d'un contexte vierge à chaque
        # cycle (priorité immédiate #1, constitution-noyau.md §12).
        previous = self._context_store.get_latest(entity_id)
        if previous is not None:
            ctx = EvaluationContext(
                entity_id=entity_id,
                base_version=previous.version,
                values=dict(previous.values),  # copie mutable, previous.values est une MappingProxyType
            )
        else:
            ctx = EvaluationContext(entity_id=entity_id)

        if fact is not None:
            candidate_ids = self._alpha_index.match(fact)
        else:
            candidate_ids = set(self._alpha_index._unindexed)

        # Tie-breaking déterministe (Q4) : reconstruire la liste de candidats
        # dans l'ordre de self._rule_order (une liste, ordre d'insertion
        # garanti) avant de trier par priorité — sinon le tri stable
        # préserverait l'ordre d'un set, qui n'est pas déterministe entre
        # exécutions (hash randomization).
        candidate_rules = [
            self._rules[rid] for rid in self._rule_order if rid in candidate_ids
        ]
        candidate_rules.sort(key=lambda r: r.priority, reverse=True)

        all_effects: list[Effect] = []
        rule_traces: list[RuleTrace] = []
        evaluation_order: list[str] = []
        has_errors = False
        rule_error_policy = self._config["rule_error_policy"]

        for candidate_rule in candidate_rules:
            evaluation_order.append(candidate_rule.rule_id)

            try:
                result = candidate_rule.evaluate(ctx, fact)
            except Exception as exc:
                rule_exc = RuleEvaluationError(candidate_rule.rule_id, exc, signal.signal_id)
                if rule_error_policy == "fail_loud":
                    raise rule_exc from exc
                has_errors = True
                rule_traces.append(RuleTrace(
                    rule_id=candidate_rule.rule_id,
                    matched=False,
                    condition_tree=ConditionTrace(
                        kind="error", description=f"crash: {exc}", result=False
                    ),
                    duration_ms=Decimal("0"),
                ))
                if rule_error_policy == "fail_fast":
                    break
                continue

            condition_tree = result.condition_trace or _NO_CONDITION_TRACE
            rule_traces.append(RuleTrace(
                rule_id=candidate_rule.rule_id,
                matched=result.matched,
                condition_tree=condition_tree,
                duration_ms=Decimal("0"),  # mesure réelle : amélioration différée
            ))

            if result.matched:
                all_effects.extend(result.effects)
                for key, value in result.context_delta.items():
                    ctx.set(key, value)
                # Étape 7 (§10) : les signaux dérivés (result.derived_signals)
                # devraient rejoindre une file d'attente interne avec
                # max_derived_depth — non câblé dans cette livraison. Un
                # signal dérivé produit ici est actuellement perdu. À faire
                # (prochaine priorité immédiate, cf. journal-integration.md).

        frozen = ctx.commit(
            causality=() if fact is None else fact.causality,
            clock=self._clock,
        )
        self._context_store.save(frozen)

        trace = DecisionTrace(
            trace_id=uuid.uuid4(),
            signal_id=signal.signal_id,
            entity_id=frozen.entity_id,
            rule_traces=tuple(rule_traces),
            context_version=frozen.version,
            evaluation_order=tuple(evaluation_order),
        )
        return Decision(
            signal_id=signal.signal_id,
            entity_id=frozen.entity_id,
            effects=tuple(all_effects),
            trace=trace,
            context_version=frozen.version,
            has_errors=has_errors,
        )

    def _ensure_not_compiled(self) -> None:
        if self._compiled:
            raise EngineAlreadyCompiledError("Impossible d'ajouter une règle après compile().")

    def _ensure_compiled(self) -> None:
        if not self._compiled:
            raise EngineNotCompiledError("evaluate() appelé avant compile().")


if __name__ == "__main__":
    from ._core import Fact
    from ._dsl import Field
    from ._testing import assert_eq, test

    def make_signal(payload: dict, entity_id: str = "e1") -> Signal:
        fact = Fact(
            fact_id=uuid.uuid4(), entity_id=entity_id, fact_type="transaction",
            _payload=payload, timestamp=Decimal("0"),
        )
        return Signal(signal_id=uuid.uuid4(), fact=fact, signal_type="transaction", timestamp=Decimal("0"))

    def test_match_and_no_match() -> None:
        engine = DecisionEngine()
        engine.add_rule(Rule(
            "rule1", priority=10, condition=Field("amount") > 100,
            action=lambda ctx, fact: Effect("alert", {"msg": "high"}, "rule1"),
        ))
        engine.add_rule(Rule(
            "rule2", priority=5, condition=Field("amount") <= 100,
            action=lambda ctx, fact: Effect("log", {"msg": "low"}, "rule2"),
        ))
        engine.compile()

        decision = engine.evaluate(make_signal({"amount": 150}))
        assert_eq(len(decision.effects), 1)
        assert_eq(decision.effects[0].effect_type, "alert")
        assert_eq(decision.has_errors, False)
        rule2_trace = [t for t in decision.trace.rule_traces if t.rule_id == "rule2"][0]
        assert_eq(rule2_trace.matched, False)
        rule1_trace = [t for t in decision.trace.rule_traces if t.rule_id == "rule1"][0]
        assert_eq(rule1_trace.condition_tree.description, "amount gt 100")
        assert_eq(rule1_trace.condition_tree.actual_value, 150)

    def test_rule_crash_continue() -> None:
        def crash(ctx: Any, fact: Any) -> None:
            raise ValueError("boom")

        engine = DecisionEngine()
        engine.add_rule(Rule("rule1", priority=10, condition=Field("amount") > 100,
                              action=lambda ctx, fact: Effect("alert", {}, "rule1")))
        engine.add_rule(Rule("rule_crash", priority=1, condition=None, action=crash))
        engine.compile()

        decision = engine.evaluate(make_signal({"amount": 150}))
        assert_eq(decision.has_errors, True)
        assert_eq(len([e for e in decision.effects if e.effect_type == "alert"]), 1)
        crash_trace = [t for t in decision.trace.rule_traces if t.rule_id == "rule_crash"][0]
        assert_eq(crash_trace.matched, False)
        assert_eq("boom" in crash_trace.condition_tree.description, True)

    def test_fail_fast_stops_remaining_rules() -> None:
        def crash(ctx: Any, fact: Any) -> None:
            raise ValueError("boom")

        engine = DecisionEngine()
        engine._config["rule_error_policy"] = "fail_fast"
        engine.add_rule(Rule("rule_crash", priority=10, condition=None, action=crash))
        engine.add_rule(Rule("rule2", priority=5, condition=Field("amount") <= 100,
                              action=lambda ctx, fact: Effect("log", {}, "rule2")))
        engine.compile()

        decision = engine.evaluate(make_signal({"amount": 50}))
        assert_eq(decision.has_errors, True)
        rule2_traces = [t for t in decision.trace.rule_traces if t.rule_id == "rule2"]
        assert_eq(len(rule2_traces), 0)

    def test_fail_loud_propagates() -> None:
        def crash(ctx: Any, fact: Any) -> None:
            raise ValueError("boom")

        engine = DecisionEngine()
        engine._config["rule_error_policy"] = "fail_loud"
        engine.add_rule(Rule("rule_crash", priority=1, condition=None, action=crash))
        engine.compile()

        try:
            engine.evaluate(make_signal({"amount": 1}))
        except RuleEvaluationError as e:
            assert_eq(e.rule_id, "rule_crash")
        else:
            raise AssertionError("fail_loud aurait dû lever RuleEvaluationError")

    def test_add_rule_rejects_duplicates_and_post_compile() -> None:
        engine = DecisionEngine()
        engine.add_rule(Rule("r1", condition=None, action=lambda ctx, fact: None))
        try:
            engine.add_rule(Rule("r1", condition=None, action=lambda ctx, fact: None))
        except DuplicateRuleError:
            pass
        else:
            raise AssertionError("duplicate rule_id devrait lever")

        engine.compile()
        try:
            engine.add_rule(Rule("r2", condition=None, action=lambda ctx, fact: None))
        except EngineAlreadyCompiledError:
            pass
        else:
            raise AssertionError("add_rule après compile() devrait lever")

    def test_evaluate_before_compile_raises() -> None:
        engine = DecisionEngine()
        try:
            engine.evaluate(make_signal({"amount": 1}))
        except EngineNotCompiledError:
            pass
        else:
            raise AssertionError("evaluate() avant compile() devrait lever")

    def test_add_rule_rejects_invalid_condition_type() -> None:
        """Trouvé par ChatGPT : condition='oops' laissait fuir une
        AttributeError brute au lieu de InvalidConditionError."""
        engine = DecisionEngine()
        try:
            engine.add_rule(Rule("bad", condition="oops", action=lambda ctx, fact: None))
        except InvalidConditionError:
            pass
        else:
            raise AssertionError("condition invalide devrait lever InvalidConditionError")

    def test_context_persists_across_two_signals() -> None:
        """Deux signaux pour la même entité doivent partager le contexte —
        sans ça, aucun compteur/score cumulé n'est possible."""
        engine = DecisionEngine()
        engine.add_rule(Rule(
            "count_visits", priority=10, condition=None,
            action=lambda ctx, fact: [{"visits": ctx.get("visits", 0) + 1}],
        ))
        engine.compile()

        d1 = engine.evaluate(make_signal({"page": "home"}, entity_id="visitor_1"))
        assert_eq(d1.context_version, 1)
        stored1 = engine._context_store.get_latest("visitor_1")
        assert_eq(stored1.values.get("visits"), 1)

        d2 = engine.evaluate(make_signal({"page": "about"}, entity_id="visitor_1"))
        assert_eq(d2.context_version, 2)
        stored2 = engine._context_store.get_latest("visitor_1")
        assert_eq(stored2.values.get("visits"), 2)

        # une autre entité ne partage pas ce compteur
        engine.evaluate(make_signal({"page": "home"}, entity_id="visitor_2"))
        stored_other = engine._context_store.get_latest("visitor_2")
        assert_eq(stored_other.values.get("visits"), 1)

    def test_tie_breaking_is_deterministic_across_many_runs() -> None:
        """À priorité égale, l'ordre d'insertion doit primer, de façon stable
        même si AlphaIndex.match() renvoie un set à l'ordre non garanti."""
        for _ in range(20):  # répété : un bug d'ordre de set ne se voit pas toujours au 1er coup
            engine = DecisionEngine()
            engine.add_rule(Rule("r1", priority=5, condition=None,
                                  action=lambda ctx, fact: Effect("e1", {}, "r1")))
            engine.add_rule(Rule("r2", priority=5, condition=None,
                                  action=lambda ctx, fact: Effect("e2", {}, "r2")))
            engine.add_rule(Rule("r3", priority=5, condition=None,
                                  action=lambda ctx, fact: Effect("e3", {}, "r3")))
            engine.compile()
            decision = engine.evaluate(make_signal({"x": 1}))
            assert_eq(decision.trace.evaluation_order, ("r1", "r2", "r3"))

    test("rule1 matche, rule2 non — vraie trace d'explicabilité présente", test_match_and_no_match)
    test("règle qui plante -> has_errors=True, les autres continuent", test_rule_crash_continue)
    test("fail_fast arrête les règles restantes", test_fail_fast_stops_remaining_rules)
    test("fail_loud propage l'exception", test_fail_loud_propagates)
    test("add_rule() : doublons et post-compile refusés", test_add_rule_rejects_duplicates_and_post_compile)
    test("evaluate() avant compile() lève EngineNotCompiledError", test_evaluate_before_compile_raises)
    test("add_rule() rejette une condition mal typée (corrigé)", test_add_rule_rejects_invalid_condition_type)
    test("le contexte persiste entre deux signaux (corrigé)", test_context_persists_across_two_signals)
    test("tie-breaking déterministe sur 20 exécutions (corrigé)", test_tie_breaking_is_deterministic_across_many_runs)

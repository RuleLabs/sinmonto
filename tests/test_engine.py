"""Tests nominaux pour sinmonto._engine — cycle d'évaluation du moteur."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sinmonto._core import Effect, Fact, Signal
from sinmonto._dsl import Field, Rule
from sinmonto._engine import DecisionEngine
from sinmonto._exceptions import MaxDerivedDepthExceededError, RuleEvaluationError


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
    assert len(decision.effects) == 1
    assert decision.effects[0].effect_type == "alert"
    assert decision.has_errors is False

    rule2_trace = [t for t in decision.trace.rule_traces if t.rule_id == "rule2"][0]
    assert rule2_trace.matched is False
    rule1_trace = [t for t in decision.trace.rule_traces if t.rule_id == "rule1"][0]
    assert rule1_trace.condition_tree.actual_value == 150


def test_rule_crash_continue() -> None:
    def crash(ctx, fact):
        raise ValueError("boom")

    engine = DecisionEngine()
    engine.add_rule(Rule("rule1", priority=10, condition=Field("amount") > 100,
                          action=lambda ctx, fact: Effect("alert", {}, "rule1")))
    engine.add_rule(Rule("rule_crash", priority=1, condition=None, action=crash))
    engine.compile()

    decision = engine.evaluate(make_signal({"amount": 150}))
    assert decision.has_errors is True
    assert len([e for e in decision.effects if e.effect_type == "alert"]) == 1
    crash_trace = [t for t in decision.trace.rule_traces if t.rule_id == "rule_crash"][0]
    assert crash_trace.matched is False
    assert "boom" in crash_trace.condition_tree.description


def test_fail_fast_stops_remaining_rules() -> None:
    def crash(ctx, fact):
        raise ValueError("boom")

    engine = DecisionEngine()
    engine._config["rule_error_policy"] = "fail_fast"
    engine.add_rule(Rule("rule_crash", priority=10, condition=None, action=crash))
    engine.add_rule(Rule("rule2", priority=5, condition=Field("amount") <= 100,
                          action=lambda ctx, fact: Effect("log", {}, "rule2")))
    engine.compile()

    decision = engine.evaluate(make_signal({"amount": 50}))
    assert decision.has_errors is True
    rule2_traces = [t for t in decision.trace.rule_traces if t.rule_id == "rule2"]
    assert len(rule2_traces) == 0


def test_fail_loud_propagates() -> None:
    def crash(ctx, fact):
        raise ValueError("boom")

    engine = DecisionEngine()
    engine._config["rule_error_policy"] = "fail_loud"
    engine.add_rule(Rule("rule_crash", priority=1, condition=None, action=crash))
    engine.compile()

    try:
        engine.evaluate(make_signal({"amount": 1}))
    except RuleEvaluationError as e:
        assert e.rule_id == "rule_crash"
    else:
        raise AssertionError("fail_loud aurait dû lever RuleEvaluationError")


def test_add_rule_rejects_duplicates_and_post_compile() -> None:
    engine = DecisionEngine()
    engine.add_rule(Rule("r1", condition=None, action=lambda ctx, fact: None))
    try:
        engine.add_rule(Rule("r1", condition=None, action=lambda ctx, fact: None))
    except Exception:
        pass
    else:
        raise AssertionError("duplicate rule_id devrait lever")

    engine.compile()
    try:
        engine.add_rule(Rule("r2", condition=None, action=lambda ctx, fact: None))
    except Exception:
        pass
    else:
        raise AssertionError("add_rule après compile() devrait lever")


def test_evaluate_before_compile_raises() -> None:
    engine = DecisionEngine()
    try:
        engine.evaluate(make_signal({"amount": 1}))
    except Exception:
        pass
    else:
        raise AssertionError("evaluate() avant compile() devrait lever")


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
    assert d1.context_version == 1
    stored1 = engine._context_store.get_latest("visitor_1")
    assert stored1.values.get("visits") == 1

    d2 = engine.evaluate(make_signal({"page": "about"}, entity_id="visitor_1"))
    assert d2.context_version == 2
    stored2 = engine._context_store.get_latest("visitor_1")
    assert stored2.values.get("visits") == 2

    # une autre entité ne partage pas ce compteur
    engine.evaluate(make_signal({"page": "home"}, entity_id="visitor_2"))
    stored_other = engine._context_store.get_latest("visitor_2")
    assert stored_other.values.get("visits") == 1


# --- Cascade de signaux dérivés (synthèse de revue croisée 5 IA, 2026-09) ---

def test_derived_signal_cascades_in_one_decision() -> None:
    """Un signal dérivé au hop 0 est traité dans le même evaluate() — une
    seule Decision agrège les effets de toute la cascade, pas une par hop."""
    def raise_flag(ctx, fact):
        derived = Signal(
            signal_id=uuid.uuid4(),
            fact=Fact(
                fact_id=uuid.uuid4(), entity_id=fact.entity_id,
                fact_type="audit_trigger", _payload={"reason": "high_amount"},
                timestamp=Decimal("0"),
            ),
            signal_type="derived", timestamp=Decimal("0"),
        )
        return [Effect("flag_raised", {}, "detect_high_amount"), derived]

    engine = DecisionEngine()
    engine.add_rule(Rule("detect_high_amount", priority=10, condition=Field("amount") > 100,
                          action=raise_flag))
    engine.add_rule(Rule("audit_on_derived", priority=5, condition=Field("reason") == "high_amount",
                          action=lambda ctx, fact: Effect("audit_logged", {}, "audit_on_derived")))
    engine.compile()

    decision = engine.evaluate(make_signal({"amount": 150}))

    assert {e.effect_type for e in decision.effects} == {"flag_raised", "audit_logged"}
    assert decision.has_errors is False
    # "audit_on_derived" n'est même pas candidat au hop 0 (son champ
    # "reason" n'existe pas sur le fact racine) — il ne peut avoir tourné
    # qu'au hop dérivé.
    hops_seen = {t.hop for t in decision.trace.rule_traces if t.rule_id == "audit_on_derived"}
    assert hops_seen == {1}


def test_cascade_context_visible_between_hops() -> None:
    """Le hop N+1 doit voir le context_delta committé par le hop N — sans
    ça, aucun score cumulatif n'est possible à travers une cascade."""
    captured: dict = {}

    def hop0(ctx, fact):
        derived = Signal(
            signal_id=uuid.uuid4(),
            fact=Fact(fact_id=uuid.uuid4(), entity_id=fact.entity_id,
                      fact_type="step2", _payload={"stage": "audit"}, timestamp=Decimal("0")),
            signal_type="derived", timestamp=Decimal("0"),
        )
        return [{"risk_score": 10}, derived]

    def hop1(ctx, fact):
        captured["risk_score_seen"] = ctx.get("risk_score", 0)
        return None

    engine = DecisionEngine()
    engine.add_rule(Rule("hop0_rule", priority=10, condition=Field("amount") > 0, action=hop0))
    engine.add_rule(Rule("hop1_rule", priority=5, condition=Field("stage") == "audit", action=hop1))
    engine.compile()

    engine.evaluate(make_signal({"amount": 50}))
    assert captured["risk_score_seen"] == 10


def test_cascade_causality_chains_through_hops() -> None:
    ids: dict = {}

    def spawn_child(ctx, fact):
        if fact.fact_type != "transaction":
            return None  # ne pas re-dériver depuis l'enfant lui-même
        ids["root_fact_id"] = fact.fact_id
        child_fact = Fact(fact_id=uuid.uuid4(), entity_id=fact.entity_id, fact_type="child",
                           _payload={}, timestamp=Decimal("0"))
        ids["child_fact_id"] = child_fact.fact_id
        return Signal(signal_id=uuid.uuid4(), fact=child_fact, signal_type="derived",
                       timestamp=Decimal("0"))

    engine = DecisionEngine()
    engine.add_rule(Rule("spawn", priority=10, condition=None, action=spawn_child))
    engine.compile()

    engine.evaluate(make_signal({"amount": 1}, entity_id="e_causal"))

    final_ctx = engine._context_store.get_latest("e_causal")
    assert ids["child_fact_id"] in final_ctx.causality
    assert ids["root_fact_id"] in final_ctx.causality
    # le hop le plus récent est en tête de la lignée
    assert final_ctx.causality.index(ids["child_fact_id"]) < \
        final_ctx.causality.index(ids["root_fact_id"])


def test_cascade_causality_correct_across_different_entities() -> None:
    """Un signal dérivé peut viser une entity_id différente de son parent
    (ex : une règle sur une transaction dérive un signal sur le compte
    destinataire). La causality du hop dérivé doit remonter jusqu'au fait
    racine même si son entity_id ne permet pas de retrouver le hop parent
    via ContextStore.get_latest (entité jamais vue avant, autre entité)."""
    def touch_other_entity(ctx, fact):
        if fact.fact_type != "transaction":
            return None
        other = Fact(fact_id=uuid.uuid4(), entity_id="entity_B", fact_type="linked",
                      _payload={}, timestamp=Decimal("0"))
        return Signal(signal_id=uuid.uuid4(), fact=other, entity_id="entity_B",
                      signal_type="derived", timestamp=Decimal("0"))

    engine = DecisionEngine()
    engine.add_rule(Rule("cross_link", priority=10, condition=None, action=touch_other_entity))
    engine.compile()

    root_signal = make_signal({"amount": 1}, entity_id="entity_A")
    engine.evaluate(root_signal)

    frozen_b = engine._context_store.get_latest("entity_B")
    assert root_signal.fact.fact_id in frozen_b.causality


def test_max_derived_depth_continue_traces_and_keeps_effects() -> None:
    def always_spawn(ctx, fact):
        child = Fact(fact_id=uuid.uuid4(), entity_id=fact.entity_id, fact_type="chain",
                     _payload={"amount": 1}, timestamp=Decimal("0"))
        derived = Signal(signal_id=uuid.uuid4(), fact=child, signal_type="derived",
                          timestamp=Decimal("0"))
        return [Effect("hop_effect", {}, "spawner"), derived]

    engine = DecisionEngine()
    engine._config["max_derived_depth"] = 1  # une seule génération de dérivés autorisée
    engine.add_rule(Rule("spawner", priority=10, condition=Field("amount") > 0, action=always_spawn))
    engine.compile()

    decision = engine.evaluate(make_signal({"amount": 1}))

    # hop0 (depth 0) spawn hop1 (depth 1, autorisé) ; hop1 tente de spawn
    # un hop2 (depth 2 > max_derived_depth=1) -> abandonné, jamais silencieux.
    assert decision.has_errors is True
    assert len(decision.effects) == 2
    depth_traces = [t for t in decision.trace.rule_traces if t.rule_id == "__max_derived_depth__"]
    assert len(depth_traces) == 1
    assert depth_traces[0].hop == 1


def test_max_derived_depth_fail_loud_raises() -> None:
    def spawn(ctx, fact):
        child = Fact(fact_id=uuid.uuid4(), entity_id=fact.entity_id, fact_type="chain",
                     _payload={}, timestamp=Decimal("0"))
        return Signal(signal_id=uuid.uuid4(), fact=child, signal_type="derived",
                      timestamp=Decimal("0"))

    engine = DecisionEngine()
    engine._config["max_derived_depth"] = 0  # aucun signal dérivé autorisé
    engine._config["rule_error_policy"] = "fail_loud"
    engine.add_rule(Rule("spawner", priority=10, condition=None, action=spawn))
    engine.compile()

    try:
        engine.evaluate(make_signal({"amount": 1}))
    except MaxDerivedDepthExceededError as e:
        assert e.depth == 1
        assert e.max_depth == 0
    else:
        raise AssertionError(
            "fail_loud + profondeur dépassée aurait dû lever MaxDerivedDepthExceededError"
        )

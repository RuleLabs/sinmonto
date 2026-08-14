"""Tests nominaux pour sinmonto._engine — cycle d'évaluation du moteur."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sinmonto._core import Effect, Fact, Signal
from sinmonto._dsl import Field, Rule
from sinmonto._engine import DecisionEngine
from sinmonto._exceptions import RuleEvaluationError


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

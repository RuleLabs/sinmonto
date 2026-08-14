"""Tests nominaux pour sinmonto._dsl — DSL de conditions et Rule."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sinmonto._core import Fact
from sinmonto._dsl import Field


def make_fact(payload: dict) -> Fact:
    return Fact(
        fact_id=uuid.uuid4(), entity_id="user_123", fact_type="user_event",
        _payload=payload, timestamp=Decimal("1700000000.0"),
    )


def test_field_condition_evaluation() -> None:
    cond = Field("age") >= 18
    trace_valid = cond.evaluate(make_fact({"age": 20}))
    assert trace_valid.result is True
    assert trace_valid.actual_value == 20

    trace_missing = cond.evaluate(make_fact({"name": "Bob"}))
    assert trace_missing.result is False
    assert trace_missing.actual_value is None

    trace_none = cond.evaluate(None)
    assert trace_none.result is False


def test_composite_and_short_circuit() -> None:
    cond = (Field("age") >= 18) & (Field("score") > 50) & (Field("vip") == True)
    trace_1 = cond.evaluate(make_fact({"age": 16, "score": 90, "vip": True}))
    assert trace_1.result is False
    assert len(trace_1.children) == 1

    trace_3 = cond.evaluate(make_fact({"age": 25, "score": 80, "vip": True}))
    assert trace_3.result is True
    # (A & B) & C empile, ne met pas à plat : 2 enfants au sommet
    assert len(trace_3.children) == 2
    assert len(trace_3.children[0].children) == 2


def test_rule_decorator_and_condition_trace() -> None:
    class DummyEngine:
        def __init__(self) -> None:
            self.rules: list = []

        def add_rule(self, r) -> None:
            self.rules.append(r)

    from sinmonto._dsl import rule, Rule

    engine = DummyEngine()

    @rule(name="rule_check_vip", priority=100, condition=Field("vip") == True, engine=engine)
    def handle_vip(ctx, fact):
        return {"effect_type": "GRANT_DISCOUNT", "payload": {"rate": 0.2}, "rule_id": "rule_check_vip"}

    assert isinstance(handle_vip, Rule)
    assert len(engine.rules) == 1

    res_vip = handle_vip.evaluate(ctx=None, fact=make_fact({"vip": True}))
    assert res_vip.matched is True
    assert len(res_vip.effects) == 0  # dict -> context_delta, pas un Effect
    assert res_vip.condition_trace.result is True

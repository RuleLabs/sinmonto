"""Tests nominaux pour sinmonto._trace — explicabilité native."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sinmonto._trace import ConditionTrace, DecisionTrace, RuleTrace


def test_condition_trace_tree_construction() -> None:
    leaf_true = ConditionTrace("field", "amount > 1000", True, actual_value=1500)
    leaf_false = ConditionTrace("field", "currency == EUR", False, actual_value="USD")
    node = ConditionTrace("and", "AND", False, children=(leaf_true, leaf_false))
    assert node.result is False
    assert len(node.children) == 2
    assert node.children[1].actual_value == "USD"


def test_decision_trace_records_evaluation_order() -> None:
    rt = RuleTrace(
        rule_id="high_risk",
        matched=True,
        condition_tree=ConditionTrace("field", "score > 80", True, actual_value=85),
        duration_ms=Decimal("0.3"),
    )
    dt = DecisionTrace(
        trace_id=uuid.uuid4(),
        signal_id=uuid.uuid4(),
        entity_id="user:1",
        rule_traces=(rt,),
        context_version=1,
        evaluation_order=("high_risk",),
    )
    assert dt.evaluation_order == ("high_risk",)
    assert dt.rule_traces[0].matched is True

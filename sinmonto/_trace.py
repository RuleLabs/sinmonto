"""ConditionTrace (arbre), RuleTrace, DecisionTrace — explicabilité native.

Dataclasses pures, aucune dépendance interne. Complet : rien à assigner ici,
la logique qui *construit* ces objets (dans FieldCondition/CompositeCondition
et dans le cycle du moteur) reste une mission ouverte ailleurs.

Test sur téléphone : `python3 -m sinmonto._trace` depuis le dossier
parent de sinmonto/.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ConditionTrace:
    kind: str  # "field" | "and" | "or" | "not" | "none" | "error"
    description: str
    result: bool
    actual_value: Any = None  # rempli seulement pour kind == "field"
    children: tuple["ConditionTrace", ...] = ()


@dataclass(frozen=True, slots=True)
class RuleTrace:
    rule_id: str
    matched: bool
    condition_tree: ConditionTrace
    duration_ms: Decimal


@dataclass(frozen=True, slots=True)
class DecisionTrace:
    trace_id: UUID
    signal_id: UUID
    entity_id: str
    rule_traces: tuple[RuleTrace, ...]
    context_version: int
    evaluation_order: tuple[str, ...]


if __name__ == "__main__":
    import uuid

    from ._testing import assert_eq, test

    def test_condition_trace_tree_construction() -> None:
        leaf_true = ConditionTrace("field", "amount > 1000", True, actual_value=1500)
        leaf_false = ConditionTrace("field", "currency == EUR", False, actual_value="USD")
        node = ConditionTrace("and", "AND", False, children=(leaf_true, leaf_false))
        assert_eq(node.result, False)
        assert_eq(len(node.children), 2)
        assert_eq(node.children[1].actual_value, "USD")

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
        assert_eq(dt.evaluation_order, ("high_risk",))
        assert_eq(dt.rule_traces[0].matched, True)

    test("Arbre ConditionTrace se construit correctement", test_condition_trace_tree_construction)
    test("DecisionTrace enregistre l'ordre d'évaluation", test_decision_trace_records_evaluation_order)

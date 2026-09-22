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
    # Ajoutés pour la cascade de signaux dérivés (2026-09) — défauts
    # rétrocompatibles, tout code qui construit un RuleTrace avec les 4
    # champs d'origine continue de fonctionner tel quel.
    hop: int = 0  # 0 = signal racine, 1 = premier dérivé, etc.
    trigger_signal_id: UUID | None = None  # signal du hop qui a déclenché cette évaluation


@dataclass(frozen=True, slots=True)
class DecisionTrace:
    trace_id: UUID
    signal_id: UUID
    entity_id: str
    rule_traces: tuple[RuleTrace, ...]
    context_version: int
    evaluation_order: tuple[str, ...]



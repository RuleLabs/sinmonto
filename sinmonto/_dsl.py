"""Field, FieldCondition, CompositeCondition — expressions de condition
indexables et composables par surcharge d'opérateurs. Rule — implémentation
concrète de Evaluable utilisée par le DSL. @rule — décorateur d'enregistrement.

Implémenté par Gemini (mission constitution-noyau.md §5), intégré avec une
correction : EvaluationResult transporte désormais `condition_trace`
(l'arbre réel produit par .evaluate()) et non plus `condition_results`
(un champ plat, hérité d'avant l'introduction de ConditionTrace en arbre —
voir la note d'intégration dans _core.py).

Test sur téléphone : `python3 -m sinmonto._dsl` depuis le dossier parent
de sinmonto/.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from ._core import Effect, EvaluationResult, Fact, Signal
from ._exceptions import InvalidConditionError, InvalidEffectError
from ._trace import ConditionTrace

__all__ = [
    "Field",
    "FieldCondition",
    "CompositeCondition",
    "Rule",
    "rule",
]


def _to_condition(val: Any) -> "FieldCondition | CompositeCondition":
    if isinstance(val, (FieldCondition, CompositeCondition)):
        return val
    raise TypeError(f"Expected FieldCondition or CompositeCondition, got {type(val).__name__}")


class Field:
    """Représente une référence de champ dans le payload d'un Fact."""

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

    def __gt__(self, value: Any) -> "FieldCondition":
        return FieldCondition(self.name, "gt", value)

    def __ge__(self, value: Any) -> "FieldCondition":
        return FieldCondition(self.name, "gte", value)

    def __lt__(self, value: Any) -> "FieldCondition":
        return FieldCondition(self.name, "lt", value)

    def __le__(self, value: Any) -> "FieldCondition":
        return FieldCondition(self.name, "lte", value)

    def __eq__(self, value: Any) -> "FieldCondition":  # type: ignore[override]
        return FieldCondition(self.name, "eq", value)

    def __ne__(self, value: Any) -> "FieldCondition":  # type: ignore[override]
        return FieldCondition(self.name, "ne", value)

    __hash__ = None  # Field.__eq__ est détourné — non hashable, assumé (§5)

    def in_(self, values: Sequence[Any]) -> "FieldCondition":
        return FieldCondition(self.name, "in", tuple(values))


_VALID_OPERATORS = frozenset({"eq", "ne", "neq", "gt", "ge", "gte", "lt", "le", "lte", "in"})


@dataclass(frozen=True, slots=True)
class FieldCondition:
    """Condition élémentaire appliquée à une propriété d'un Fact."""

    field_name: str
    operator: str
    reference: Any

    def __post_init__(self) -> None:
        # Avant : un opérateur inconnu (ex. faute de frappe "gtt") ne levait
        # jamais rien, nulle part — evaluate() retournait juste False en
        # silence, pour toujours. Contraire à "fail loud" (constitution-
        # finale.md). Validé ici, au moment le plus tôt possible — avant même
        # add_rule()/compile(). Trouvé en revue croisée (ChatGPT, Qwen,
        # Kimi) — 2026-08.
        if self.operator not in _VALID_OPERATORS:
            raise InvalidConditionError(
                f"Opérateur FieldCondition inconnu: {self.operator!r}. "
                f"Attendu l'un de: {sorted(_VALID_OPERATORS)}"
            )

    def __and__(self, other: Any) -> "CompositeCondition":
        return CompositeCondition("and", (self, _to_condition(other)))

    def __or__(self, other: Any) -> "CompositeCondition":
        return CompositeCondition("or", (self, _to_condition(other)))

    def __invert__(self) -> "CompositeCondition":
        return CompositeCondition("not", (self,))

    def evaluate(self, fact: Fact | None) -> ConditionTrace:
        """Évalue la condition sur le fait fourni. Si fact est None ou si la
        clé est absente, retourne False sans exception."""
        desc = f"{self.field_name} {self.operator} {self.reference!r}"

        if fact is None or self.field_name not in fact.payload:
            return ConditionTrace(
                kind="field", description=desc, result=False, actual_value=None, children=()
            )

        actual_value = fact.payload[self.field_name]
        res = False
        try:
            op = self.operator
            if op == "eq":
                res = actual_value == self.reference
            elif op in ("ne", "neq"):
                res = actual_value != self.reference
            elif op == "gt":
                res = actual_value > self.reference
            elif op in ("ge", "gte"):
                res = actual_value >= self.reference
            elif op == "lt":
                res = actual_value < self.reference
            elif op in ("le", "lte"):
                res = actual_value <= self.reference
            elif op == "in":
                res = actual_value in self.reference
        except (TypeError, ValueError):
            res = False

        return ConditionTrace(
            kind="field", description=desc, result=bool(res), actual_value=actual_value, children=()
        )


_VALID_KINDS = frozenset({"and", "or", "not"})


@dataclass(frozen=True, slots=True)
class CompositeCondition:
    """Combinaison booléenne (AND, OR, NOT) de conditions."""

    kind: str
    children: tuple["FieldCondition | CompositeCondition", ...]

    def __post_init__(self) -> None:
        # Avant : un kind inconnu (ex. "xor") ne levait ValueError qu'à
        # evaluate() — trop tard, après add_rule()/compile(). Validé ici
        # pour un vrai fail-loud à la construction. Trouvé en revue croisée
        # (Qwen) — 2026-08.
        if self.kind.lower() not in _VALID_KINDS:
            raise InvalidConditionError(
                f"Kind de condition composite inconnu: {self.kind!r}. "
                f"Attendu l'un de: {sorted(_VALID_KINDS)}"
            )

    def __and__(self, other: Any) -> "CompositeCondition":
        return CompositeCondition("and", (self, _to_condition(other)))

    def __or__(self, other: Any) -> "CompositeCondition":
        return CompositeCondition("or", (self, _to_condition(other)))

    def __invert__(self) -> "CompositeCondition":
        return CompositeCondition("not", (self,))

    def evaluate(self, fact: Fact | None) -> ConditionTrace:
        """Évalue l'arbre de conditions. Court-circuit sur AND et OR : les
        branches non évaluées n'apparaissent pas dans children."""
        kind_lower = self.kind.lower()

        if kind_lower == "and":
            child_traces: list[ConditionTrace] = []
            overall_result = True
            for child in self.children:
                trace = child.evaluate(fact)
                child_traces.append(trace)
                if not trace.result:
                    overall_result = False
                    break
            return ConditionTrace(
                kind="and", description="AND", result=overall_result,
                actual_value=None, children=tuple(child_traces),
            )

        elif kind_lower == "or":
            child_traces = []
            overall_result = False
            for child in self.children:
                trace = child.evaluate(fact)
                child_traces.append(trace)
                if trace.result:
                    overall_result = True
                    break
            return ConditionTrace(
                kind="or", description="OR", result=overall_result,
                actual_value=None, children=tuple(child_traces),
            )

        elif kind_lower == "not":
            if not self.children:
                return ConditionTrace(kind="not", description="NOT", result=True, children=())
            child_trace = self.children[0].evaluate(fact)
            return ConditionTrace(
                kind="not", description="NOT", result=not child_trace.result,
                children=(child_trace,),
            )

        else:
            raise ValueError(f"Unknown condition kind: {self.kind}")


class Rule:
    """Implémentation standard du protocole Evaluable pour les règles DSL."""

    __slots__ = ("rule_id", "priority", "condition", "action")

    def __init__(
        self,
        rule_id: str,
        priority: int = 0,
        condition: "FieldCondition | CompositeCondition | None" = None,
        action: Callable[..., Any] | None = None,
    ) -> None:
        self.rule_id = rule_id
        self.priority = priority
        self.condition = condition
        self.action = action

    def evaluate(self, ctx: Any, fact: Fact | None) -> EvaluationResult:
        cond_trace: ConditionTrace | None = None

        if self.condition is not None:
            cond_trace = self.condition.evaluate(fact)
            cond_matched = cond_trace.result
        else:
            cond_matched = True

        if not cond_matched:
            return EvaluationResult(
                matched=False,
                effects=(),
                derived_signals=(),
                context_delta={},
                condition_trace=cond_trace,
            )

        effects: list[Effect] = []
        derived_signals: list[Signal] = []
        context_delta: dict[str, Any] = {}

        if self.action is not None:
            res = self.action(ctx, fact)
            if res is None:
                pass
            elif isinstance(res, Effect):
                effects.append(res)
            elif isinstance(res, Signal):
                derived_signals.append(res)
            elif isinstance(res, dict):
                context_delta.update(res)
            elif isinstance(res, (list, tuple)):
                for item in res:
                    if isinstance(item, Effect):
                        effects.append(item)
                    elif isinstance(item, Signal):
                        derived_signals.append(item)
                    elif isinstance(item, dict):
                        context_delta.update(item)
                    else:
                        raise InvalidEffectError(
                            f"Élément non reconnu dans le retour de l'action "
                            f"'{self.rule_id}': {type(item).__name__}. "
                            "Attendu Effect, Signal ou dict."
                        )
            else:
                # Avant : un retour non reconnu (int, str, EvaluationResult
                # direct...) était silencieusement ignoré — matched=True mais
                # 0 effet, sans trace ni erreur, le moteur "mentait poliment".
                # EvaluationResult direct est maintenant explicitement
                # interdit : ça permettait à une action d'écraser le
                # condition_trace déjà calculé par la règle, une deuxième
                # voie de mutation qui contourne la trace construite plus
                # haut. Trouvé en revue croisée (ChatGPT, Qwen) — 2026-08.
                raise InvalidEffectError(
                    f"Retour d'action non reconnu pour la règle "
                    f"'{self.rule_id}': {type(res).__name__}. Attendu None, "
                    "Effect, Signal, dict, ou une liste/tuple de ceux-ci."
                )

        return EvaluationResult(
            matched=True,
            effects=tuple(effects),
            derived_signals=tuple(derived_signals),
            context_delta=context_delta,
            condition_trace=cond_trace,
        )


def rule(
    rule_id_or_func: "str | Callable[..., Any] | None" = None,
    *,
    name: str | None = None,
    priority: int = 0,
    condition: "FieldCondition | CompositeCondition | None" = None,
    engine: Any | None = None,
) -> Any:
    """Décorateur d'enregistrement de règle pour le DecisionEngine.

    API supportée :
      - @rule(name="mon_nom", priority=10, condition=cond)
      - @rule("mon_id", priority=10, condition=cond, engine=engine)
      - @rule (sans arguments, utilise le nom de la fonction)
    """

    def _register(r: Rule) -> None:
        if engine is None:
            return
        if hasattr(engine, "add_rule"):
            engine.add_rule(r)
        elif hasattr(engine, "register"):
            engine.register(r)
        elif hasattr(engine, "register_rule"):
            engine.register_rule(r)

    def decorator(fn: Callable[..., Any]) -> Rule:
        r_id = name or (rule_id_or_func if isinstance(rule_id_or_func, str) else None) or fn.__name__
        r = Rule(rule_id=r_id, priority=priority, condition=condition, action=fn)
        _register(r)
        return r

    if callable(rule_id_or_func):
        fn = rule_id_or_func
        r_id = name or fn.__name__
        r = Rule(rule_id=r_id, priority=priority, condition=condition, action=fn)
        _register(r)
        return r

    return decorator



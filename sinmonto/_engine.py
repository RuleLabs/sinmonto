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

Revue croisée multi-IA du 2026-08 (ChatGPT, Grok, DeepSeek, Kimi, Qwen,
Meta AI) — corrections d'atomicité et de causalité :
- Reload de previous.values et commit() : deepcopy au lieu d'une copie
  superficielle (une valeur imbriquée mutée ne corrompt plus rétroactivement
  un FrozenContext déjà figé).
- Snapshot/restore de ctx._values autour de chaque rule.evaluate() : une
  action qui appelle ctx.set() directement puis plante ne laisse plus sa
  mutation survivre au commit final. except Exception reste tel quel
  (ne PAS élargir à BaseException — SystemExit/KeyboardInterrupt doivent
  rester interruptibles ; élargir n'aurait de toute façon rien changé au
  problème d'atomicité, la mutation a déjà eu lieu avant que l'exception
  ne soit levée).
- causality : (fact.fact_id, *fact.causality) pour un fait au lieu de
  fact.causality seul ; (signal.signal_id,) pour un timer au lieu de ().

Test sur téléphone : `python3 -m sinmonto._engine` depuis le dossier
parent de sinmonto/.
"""

from __future__ import annotations

import copy
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
                # deepcopy et non dict(...) : previous.values contient
                # potentiellement des listes/dicts imbriqués qui, avec une
                # copie superficielle, resteraient partagés avec le
                # FrozenContext précédent — une mutation ici le corromprait
                # rétroactivement. Trouvé en revue croisée (Qwen, Kimi).
                values=copy.deepcopy(dict(previous.values)),
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

            # Snapshot avant l'évaluation : si l'action mute ctx directement
            # (ctx.set(), ou mutation en place d'un objet imbriqué) puis
            # plante, cette mutation ne doit pas survivre au commit final —
            # "une règle qui plante n'applique jamais partiellement son
            # context_delta" (constitution-finale.md Q5). deepcopy pour
            # attraper aussi une mutation d'objet imbriqué, pas seulement
            # ctx.set() au premier niveau. Trouvé en revue croisée (Kimi,
            # Grok, Meta AI, Qwen) — 2026-08.
            values_snapshot = copy.deepcopy(ctx._values)

            try:
                result = candidate_rule.evaluate(ctx, fact)
            except Exception as exc:
                ctx._values = values_snapshot  # rollback — tout ou rien
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
            # Avant : () pour un timer, fact.causality seul pour un fait —
            # perdait l'origine immédiate dans les deux cas. Verrouillé en
            # revue croisée (proposition initiale validée par ChatGPT/Grok/
            # Kimi/Qwen/Meta AI) — 2026-08.
            causality=(
                (fact.fact_id, *fact.causality) if fact is not None
                else (signal.signal_id,)
            ),
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



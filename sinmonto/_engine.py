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

Cascade de signaux dérivés câblée (2026-09), synthèse de revue croisée
5 IA (Kimi, ChatGPT/Luna, Grok, Gemini, Qwen) sur la mission ouverte
depuis rc3 — voir docs/journal-integration.md pour le détail complet :
- File FIFO locale à evaluate() (consensus unanime des 5, déjà verrouillé
  par constitution-finale.md §7 "jamais réinjectés dans le même cycle") :
  chaque hop est un cycle d'évaluation complet avec son propre commit(),
  tous orchestrés dans ce seul appel Python. Aucune Decision n'est
  assemblée avant épuisement complet de la file — résout la tension de
  l'ancien §10 (constitution-noyau.md) où l'étape 9 ("Decision assemblée
  et retournée") précédait l'étape 10 ("file traitée après").
- max_derived_depth dépassé : gouverné par rule_error_policy, comme le
  reste d'EngineRuntimeError (déjà le cas pour RuleEvaluationError) plutôt
  qu'un axe de policy séparé — fail_loud lève MaxDerivedDepthExceededError,
  continue/fail_fast tracent (rule_id="__max_derived_depth__") et mettent
  has_errors=True sans jamais abandonner silencieusement un signal.
- causality par hop : (fact.fact_id, *fact.causality) ou (signal_id,) pour
  CE hop, préfixé à la causality du hop parent — généralisation directe de
  la formule racine existante (parent = () pour la racine), transportée
  explicitement dans la file plutôt que relue via
  ContextStore.get_latest(entity_id), pour rester correcte si un signal
  dérivé cible une entity_id différente de son parent.
- RuleTrace gagne hop/trigger_signal_id (défauts rétrocompatibles) pour
  distinguer deux évaluations du même rule_id à des hops différents.

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
    MaxDerivedDepthExceededError,
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

        max_depth: int = self._config["max_derived_depth"]
        rule_error_policy = self._config["rule_error_policy"]

        # File FIFO locale à CET appel — aucun état de cascade ne survit
        # entre deux evaluate(). Chaque élément porte la causality de son
        # PARENT (tuple explicite, pas relu via ContextStore.get_latest
        # par entity_id : un signal dérivé peut viser une entity_id
        # différente de son parent, auquel cas ce rechargement irait
        # chercher un contexte sans rapport avec la cascade en cours).
        # () pour le hop racine : sa propre contribution (calculée en
        # début de boucle) n'a rien devant elle.
        queue: list[tuple[Signal, int, tuple[uuid.UUID, ...]]] = [(signal, 0, ())]

        all_effects: list[Effect] = []
        rule_traces: list[RuleTrace] = []
        evaluation_order: list[str] = []
        has_errors = False

        while queue:
            current_signal, depth, parent_causality = queue.pop(0)
            fact = current_signal.fact

            if fact is not None:
                self._fact_store.append(fact)

            # Contribution causale de CE hop, préfixée à la lignée du
            # parent — généralisation directe de la formule qui existait
            # déjà pour la racine (parent_causality = () dans ce cas,
            # donc le résultat est identique à avant pour un evaluate()
            # sans cascade).
            own_contribution = (
                (fact.fact_id, *fact.causality) if fact is not None
                else (current_signal.signal_id,)
            )
            this_hop_causality = own_contribution + parent_causality

            entity_id = current_signal.entity_id

            # Persistance du contexte : reprend le dernier FrozenContext
            # connu de CETTE entité (constitution-noyau.md §12). Rechargé à
            # chaque hop, y compris pour la racine — un hop dérivé doit voir
            # les context_delta déjà committés par le hop précédent.
            previous = self._context_store.get_latest(entity_id)
            if previous is not None:
                ctx = EvaluationContext(
                    entity_id=entity_id,
                    base_version=previous.version,
                    # deepcopy et non dict(...) : previous.values contient
                    # potentiellement des listes/dicts imbriqués qui, avec
                    # une copie superficielle, resteraient partagés avec le
                    # FrozenContext précédent — une mutation ici le
                    # corromprait rétroactivement. Trouvé en revue croisée
                    # (Qwen, Kimi).
                    values=copy.deepcopy(dict(previous.values)),
                )
            else:
                ctx = EvaluationContext(entity_id=entity_id)

            if fact is not None:
                candidate_ids = self._alpha_index.match(fact)
            else:
                candidate_ids = set(self._alpha_index._unindexed)

            # Tie-breaking déterministe (Q4) : reconstruire la liste de
            # candidats dans l'ordre de self._rule_order (une liste, ordre
            # d'insertion garanti) avant de trier par priorité — sinon le
            # tri stable préserverait l'ordre d'un set, qui n'est pas
            # déterministe entre exécutions (hash randomization).
            candidate_rules = [
                self._rules[rid] for rid in self._rule_order if rid in candidate_ids
            ]
            candidate_rules.sort(key=lambda r: r.priority, reverse=True)

            for candidate_rule in candidate_rules:
                evaluation_order.append(candidate_rule.rule_id)

                # Snapshot avant l'évaluation : si l'action mute ctx
                # directement (ctx.set(), ou mutation en place d'un objet
                # imbriqué) puis plante, cette mutation ne doit pas survivre
                # au commit final — "une règle qui plante n'applique jamais
                # partiellement son context_delta" (constitution-finale.md
                # Q5). deepcopy pour attraper aussi une mutation d'objet
                # imbriqué, pas seulement ctx.set() au premier niveau.
                # Trouvé en revue croisée (Kimi, Grok, Meta AI, Qwen) —
                # 2026-08.
                values_snapshot = copy.deepcopy(ctx._values)

                try:
                    result = candidate_rule.evaluate(ctx, fact)
                except Exception as exc:
                    ctx._values = values_snapshot  # rollback — tout ou rien
                    rule_exc = RuleEvaluationError(
                        candidate_rule.rule_id, exc, current_signal.signal_id
                    )
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
                        hop=depth,
                        trigger_signal_id=current_signal.signal_id,
                    ))
                    if rule_error_policy == "fail_fast":
                        # Arrête les règles restantes de CE hop uniquement
                        # (constitution-finale.md Q5 : "arrête les règles
                        # restantes de ce cycle") — les hops déjà enfilés
                        # par des règles précédentes de ce même hop restent
                        # valides et la cascade continue.
                        break
                    continue

                condition_tree = result.condition_trace or _NO_CONDITION_TRACE
                rule_traces.append(RuleTrace(
                    rule_id=candidate_rule.rule_id,
                    matched=result.matched,
                    condition_tree=condition_tree,
                    duration_ms=Decimal("0"),  # mesure réelle : amélioration différée
                    hop=depth,
                    trigger_signal_id=current_signal.signal_id,
                ))

                if not result.matched:
                    continue

                all_effects.extend(result.effects)
                for key, value in result.context_delta.items():
                    ctx.set(key, value)

                for derived_signal in result.derived_signals:
                    child_depth = depth + 1
                    if child_depth > max_depth:
                        if rule_error_policy == "fail_loud":
                            raise MaxDerivedDepthExceededError(
                                signal_id=derived_signal.signal_id,
                                depth=child_depth,
                                max_depth=max_depth,
                            )
                        # continue/fail_fast : jamais silencieux — tracé
                        # explicitement, has_errors=True, le signal dérivé
                        # en cause est abandonné mais le reste de la
                        # cascade (et les effets déjà produits) survit.
                        has_errors = True
                        rule_traces.append(RuleTrace(
                            rule_id="__max_derived_depth__",
                            matched=False,
                            condition_tree=ConditionTrace(
                                kind="error",
                                description=(
                                    f"max_derived_depth ({max_depth}) "
                                    f"dépassé — signal {derived_signal.signal_id} "
                                    "abandonné"
                                ),
                                result=False,
                            ),
                            duration_ms=Decimal("0"),
                            hop=depth,
                            trigger_signal_id=current_signal.signal_id,
                        ))
                        continue
                    queue.append((derived_signal, child_depth, this_hop_causality))

            # Commit de CE hop — jamais réinjecté dans le même cycle
            # (constitution-finale.md §7) : le hop suivant, s'il y en a un,
            # rechargera ce FrozenContext fraîchement sauvegardé au tour
            # suivant de la boucle `while queue`.
            frozen = ctx.commit(causality=this_hop_causality, clock=self._clock)
            self._context_store.save(frozen)

        # Decision agrégée pour toute la cascade, assemblée seulement après
        # épuisement complet de la file — plus jamais "Decision retournée
        # puis file traitée après" (ancien §10, constitution-noyau.md).
        # signal_id/entity_id restent ceux du signal RACINE tout du long
        # (comme avant l'introduction de la cascade) : Decision représente
        # le résultat de l'évaluation de CE signal-là, même si la cascade a
        # traversé d'autres entity_id en chemin. Leurs propres FrozenContext
        # sont bien committés et interrogeables via ContextStore, juste pas
        # résumés en tête de cette Decision — pas de concept multi-entity
        # dans le contrat public pour cette preview.
        final_context = self._context_store.get_latest(signal.entity_id)
        # Le hop racine (depth=0) tourne et committe toujours, quel que
        # soit max_derived_depth (qui ne borne que les hops dérivés) :
        # final_context est donc garanti non None ici.
        assert final_context is not None
        context_version = final_context.version

        trace = DecisionTrace(
            trace_id=uuid.uuid4(),
            signal_id=signal.signal_id,
            entity_id=signal.entity_id,
            rule_traces=tuple(rule_traces),
            context_version=context_version,
            evaluation_order=tuple(evaluation_order),
        )
        return Decision(
            signal_id=signal.signal_id,
            entity_id=signal.entity_id,
            effects=tuple(all_effects),
            trace=trace,
            context_version=context_version,
            has_errors=has_errors,
        )

    def _ensure_not_compiled(self) -> None:
        if self._compiled:
            raise EngineAlreadyCompiledError("Impossible d'ajouter une règle après compile().")

    def _ensure_compiled(self) -> None:
        if not self._compiled:
            raise EngineNotCompiledError("evaluate() appelé avant compile().")



"""Objets fondamentaux : temps injecté, Fait, Signal, Effet, Décision.

Ne dépend que de la stdlib. Les annotations vers EvaluationContext et
DecisionTrace (définis dans _context.py et _trace.py) restent volontairement
non importées : `from __future__ import annotations` les rend paresseuses,
ce qui évite un cycle d'import (_context.py a besoin de Fact, défini ici).
Voir constitution-noyau.md §11 — c'est exactement le "Piège 1" que Kimi a
signalé lors de la revue Q6.

Les tests pour ce module sont dans tests/test_core.py et
tests/test_regressions.py (déplacés hors du package en Phase 3 de la
restructuration, 2026-08) : `python3 tests/run_all.py test_core` depuis la
racine du dépôt.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Mapping, Protocol
from uuid import UUID


class Clock(Protocol):
    """Temps injecté. Jamais time.time() appelé directement dans le moteur."""

    def now(self) -> Decimal: ...


class ManualClock:
    """Horloge manuelle — pour les tests et le futur replay."""

    __slots__ = ("_current",)

    def __init__(self, start: Decimal = Decimal(0)) -> None:
        self._current = start

    def now(self) -> Decimal:
        return self._current

    def set(self, value: Decimal) -> None:
        self._current = value


@dataclass(frozen=True, slots=True)
class Fact:
    """Information contextuelle, immuable. Ne déclenche jamais une évaluation
    par elle-même — voir Signal."""

    fact_id: UUID
    entity_id: str
    fact_type: str
    _payload: dict[str, Any]
    timestamp: Decimal
    causality: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        # Copie défensive : sans ça, un appelant qui garde une référence au
        # dict passé en _payload peut le muter après coup et le Fact change
        # silencieusement malgré frozen=True. La propriété .payload protège
        # déjà la lecture (MappingProxyType) mais pas la construction.
        # Trouvé en revue croisée (Kimi, Qwen) — 2026-08.
        #
        # deepcopy et non dict() superficiel : un dict() ne protège que le
        # premier niveau — une liste ou un dict imbriqué dans le payload
        # restait partagé, mutable de l'extérieur après construction. Un
        # Fact qui prétend être figé mais laisse fuir ses valeurs imbriquées
        # n'est pas vraiment figé. Trouvé en re-revue (ChatGPT, Grok) —
        # 2026-08, sur le tour suivant.
        object.__setattr__(self, "_payload", copy.deepcopy(self._payload))

    @property
    def payload(self) -> Mapping[str, Any]:
        return MappingProxyType(self._payload)


@dataclass(frozen=True, slots=True)
class Signal:
    """Déclencheur d'un cycle d'évaluation. `fact` vaut None pour un timer.

    `entity_id` : dérivé automatiquement de `fact.entity_id` si non fourni et
    qu'un `fact` est présent. Obligatoire explicitement quand `fact` est
    `None` (signal timer) — sans quoi il n'y a aucun moyen de savoir à quelle
    entité le signal se rapporte. Trouvé par Kimi/DeepSeek en revue : avant
    cette correction, le moteur assignait "global" à tous les timers,
    fusionnant silencieusement leurs contextes.
    """

    signal_id: UUID
    fact: Fact | None
    signal_type: str
    timestamp: Decimal
    entity_id: str | None = None

    def __post_init__(self) -> None:
        if self.entity_id is None:
            if self.fact is not None:
                object.__setattr__(self, "entity_id", self.fact.entity_id)
            else:
                raise ValueError(
                    "Signal.entity_id est obligatoire quand fact est None "
                    "(signal timer) — impossible de le déduire."
                )
        elif self.fact is not None and self.entity_id != self.fact.entity_id:
            # entity_id explicite en désaccord avec fact.entity_id : sans ce
            # check, le moteur suit signal.entity_id pour l'évaluation pendant
            # que le Fact reste stocké sous une autre entité — une séparation
            # silencieuse entre les deux qui corrompt le contexte. Trouvé par
            # ChatGPT en revue — 2026-08.
            raise ValueError(
                f"Signal.entity_id ({self.entity_id!r}) ne correspond pas à "
                f"fact.entity_id ({self.fact.entity_id!r}). Utiliser le même "
                "entity_id des deux côtés, ou ne pas le fournir pour qu'il "
                "soit dérivé automatiquement du fact."
            )


@dataclass(frozen=True, slots=True)
class Effect:
    """Effet de bord décrit, jamais exécuté par le moteur lui-même."""

    effect_type: str
    payload: Mapping[str, Any]
    rule_id: str

    def __post_init__(self) -> None:
        # Effect.payload n'avait aucune protection — ni copie, ni
        # MappingProxyType, contrairement à Fact.payload. Un Effect stocké
        # dans une trace/un log d'audit devrait être aussi figé qu'un Fact.
        # deepcopy pour la même raison que Fact._payload ci-dessus (valeurs
        # imbriquées), MappingProxyType pour bloquer aussi une réaffectation
        # de clé au premier niveau après coup. Trouvé en revue croisée
        # (Grok) — 2026-08.
        object.__setattr__(self, "payload", MappingProxyType(copy.deepcopy(self.payload)))


class Evaluable(Protocol):
    """Contrat commun implémenté par Rule, Transition (à venir)."""

    rule_id: str
    priority: int

    def evaluate(self, ctx: EvaluationContext, fact: Fact | None) -> EvaluationResult: ...


@dataclass(slots=True)
class EvaluationResult:
    """Créé à chaque évaluation de règle, potentiellement des milliers de
    fois par cycle — slots=True ajouté ici (trouvé manquant en revue,
    c'était le seul objet chaud à y échapper, §9)."""

    matched: bool
    effects: tuple[Effect, ...]
    derived_signals: tuple[Signal, ...]
    context_delta: Mapping[str, Any]
    condition_trace: ConditionTrace | None
    # CORRECTION D'INTÉGRATION : ce champ s'appelait condition_results
    # (Mapping[str, bool]) — un reliquat d'avant l'introduction de l'arbre
    # ConditionTrace. Gemini (_dsl.py) et DeepSeek pro (_engine.py) ont chacun
    # dû contourner ce trou différemment (l'un l'a laissé vide, l'autre a
    # reconstruit une trace plate synthétique côté moteur). condition_trace
    # transporte maintenant le vrai arbre produit par
    # FieldCondition/CompositeCondition.evaluate() — voir constitution-noyau.md
    # §1 et §5. ConditionTrace est défini dans _trace.py ; référencé ici en
    # lazy (from __future__ import annotations) pour ne pas créer de cycle,
    # même logique que EvaluationContext et DecisionTrace juste au-dessus.


@dataclass(frozen=True, slots=True)
class Decision:
    signal_id: UUID
    entity_id: str
    effects: tuple[Effect, ...]
    trace: DecisionTrace
    context_version: int
    has_errors: bool = False


class _EngineJSONEncoder(json.JSONEncoder):
    """Encodeur JSON pour Decimal, UUID, bytes. Jamais pickle."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return {"__type": "Decimal", "value": str(obj)}
        if isinstance(obj, UUID):
            return {"__type": "UUID", "value": str(obj)}
        if isinstance(obj, bytes):
            return {"__type": "bytes", "value": obj.decode("utf-8")}
        return super().default(obj)



"""Objets fondamentaux : temps injecté, Fait, Signal, Effet, Décision.

Ne dépend que de la stdlib. Les annotations vers EvaluationContext et
DecisionTrace (définis dans _context.py et _trace.py) restent volontairement
non importées : `from __future__ import annotations` les rend paresseuses,
ce qui évite un cycle d'import (_context.py a besoin de Fact, défini ici).
Voir constitution-noyau.md §11 — c'est exactement le "Piège 1" que Kimi a
signalé lors de la revue Q6.

Pour tester ce fichier isolément sur téléphone, exécuter depuis le dossier
PARENT de sinmonto/ : `python3 -m sinmonto._core` (pas
`python3 _core.py` directement — l'import relatif de _testing a besoin que
Python connaisse le package parent).
"""

from __future__ import annotations

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


@dataclass(frozen=True, slots=True)
class Effect:
    """Effet de bord décrit, jamais exécuté par le moteur lui-même."""

    effect_type: str
    payload: Mapping[str, Any]
    rule_id: str


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


if __name__ == "__main__":
    import uuid

    from ._testing import assert_eq, test

    def test_fact_payload_is_read_only() -> None:
        f = Fact(
            fact_id=uuid.uuid4(),
            entity_id="user:1",
            fact_type="transaction",
            _payload={"amount": 1500},
            timestamp=Decimal("0"),
        )
        assert_eq(f.payload["amount"], 1500)
        try:
            f.payload["amount"] = 9999  # type: ignore[index]
        except TypeError:
            pass
        else:
            raise AssertionError("payload should be read-only")

    def test_manual_clock() -> None:
        clock = ManualClock(Decimal("100"))
        assert_eq(clock.now(), Decimal("100"))
        clock.set(Decimal("200"))
        assert_eq(clock.now(), Decimal("200"))

    def test_json_encoder_handles_decimal_and_uuid() -> None:
        uid = uuid.uuid4()
        encoded = json.dumps({"amount": Decimal("10.5"), "id": uid}, cls=_EngineJSONEncoder)
        assert_eq(json.loads(encoded)["amount"]["value"], "10.5")
        assert_eq(json.loads(encoded)["id"]["value"], str(uid))

    def test_signal_entity_id_derived_from_fact() -> None:
        f = Fact(
            fact_id=uuid.uuid4(), entity_id="user:42", fact_type="t",
            _payload={}, timestamp=Decimal("0"),
        )
        s = Signal(signal_id=uuid.uuid4(), fact=f, signal_type="t", timestamp=Decimal("0"))
        assert_eq(s.entity_id, "user:42")

    def test_signal_requires_explicit_entity_id_without_fact() -> None:
        try:
            Signal(signal_id=uuid.uuid4(), fact=None, signal_type="timer", timestamp=Decimal("0"))
        except ValueError:
            pass
        else:
            raise AssertionError("un signal timer sans entity_id explicite devrait lever")

        # avec entity_id explicite, ça marche
        s = Signal(
            signal_id=uuid.uuid4(), fact=None, signal_type="timer",
            timestamp=Decimal("0"), entity_id="user:99",
        )
        assert_eq(s.entity_id, "user:99")

    test("Fact.payload est réellement en lecture seule", test_fact_payload_is_read_only)
    test("ManualClock get/set", test_manual_clock)
    test("_EngineJSONEncoder gère Decimal et UUID", test_json_encoder_handles_decimal_and_uuid)
    test("Signal.entity_id dérivé du fact", test_signal_entity_id_derived_from_fact)
    test("Signal timer exige entity_id explicite", test_signal_requires_explicit_entity_id_without_fact)

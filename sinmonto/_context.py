from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID

from ._core import Fact


@dataclass(frozen=True, slots=True)
class FrozenContext:
    """Snapshot post-évaluation. Immuable, sérialisable. Base du replay.

    Délibérément NON hashable — `values` est un conteneur métier arbitraire
    (peut contenir des listes, des dicts imbriqués...) qu'on ne peut pas
    garantir hashable en général. `__hash__ = None` rend l'échec explicite
    et immédiat plutôt qu'une TypeError profonde et confuse au moment où
    Python tenterait de hasher `values` en interne. Trouvé par ChatGPT en
    revue : la docstring précédente promettait "hashable" à tort — cette
    propriété n'a jamais été verrouillée dans constitution-noyau.md, c'était
    un reliquat d'une proposition très ancienne, jamais retenue.
    """
    entity_id: str
    version: int
    values: Mapping[str, Any]
    causality: tuple[UUID, ...]
    timestamp: Decimal

    __hash__ = None  # explicite — voir docstring

    def __post_init__(self) -> None:
        # Protection réelle : si values est un dict mutable, le transformer
        # en MappingProxyType. Nécessaire pour les objets créés manuellement
        # ou via désérialisation, pas seulement via commit().
        if isinstance(self.values, dict):
            object.__setattr__(
                self, "values", MappingProxyType(self.values)
            )


class ContextStore(ABC):
    """Persiste le dernier FrozenContext connu par entité — sans ça, chaque
    evaluate() repart de zéro (trouvé en faisant tourner le moteur, priorité
    immédiate #1 de constitution-noyau.md §12)."""

    @abstractmethod
    def get_latest(self, entity_id: str) -> FrozenContext | None: ...

    @abstractmethod
    def save(self, frozen: FrozenContext) -> None: ...


class InMemoryContextStore(ContextStore):
    """Implémentation par défaut du cœur — même logique que InMemoryFactStore."""

    def __init__(self) -> None:
        self._latest: dict[str, FrozenContext] = {}

    def get_latest(self, entity_id: str) -> FrozenContext | None:
        return self._latest.get(entity_id)

    def save(self, frozen: FrozenContext) -> None:
        self._latest[frozen.entity_id] = frozen


class EvaluationContext:
    """Mutable. Vit uniquement pendant un appel à engine.evaluate()."""
    __slots__ = ("entity_id", "_base_version", "_values")

    def __init__(
        self,
        entity_id: str,
        base_version: int = 0,
        values: dict[str, Any] | None = None,
    ) -> None:
        self.entity_id = entity_id
        self._base_version = base_version
        self._values = values if values is not None else {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._values[key] = value

    def commit(self, causality: tuple[UUID, ...], clock) -> FrozenContext:
        """Figez le contexte courant en un FrozenContext immuable.

        La version est incrémentée depuis ``self._base_version``.
        Le timestamp est lu depuis ``clock.now()`` — jamais ``time.time()``.
        Les values sont isolées par copie puis protégées par
        ``MappingProxyType`` (même logique que ``Fact.payload``).
        """
        return FrozenContext(
            entity_id=self.entity_id,
            version=self._base_version + 1,
            values=MappingProxyType(self._values.copy()),
            causality=causality,
            timestamp=clock.now(),
        )


class FactStore(ABC):
    """Stockage append-only de faits, indexé par entité et temps."""

    @abstractmethod
    def append(self, fact: Fact) -> None:
        ...

    @abstractmethod
    def get(self, fact_id: UUID) -> Fact | None:
        ...

    @abstractmethod
    def query(
        self,
        entity_id: str,
        since: Decimal | None = None,
        until: Decimal | None = None,
    ) -> tuple[Fact, ...]:
        ...


class InMemoryFactStore(FactStore):
    """Implémentation par défaut du cœur. Ring buffer, mémoire bornée."""

    def __init__(self, max_facts: int = 100_000) -> None:
        self._facts: dict[UUID, Fact] = {}
        self._order: deque[UUID] = deque(maxlen=max_facts)

    def append(self, fact: Fact) -> None:
        if len(self._order) == self._order.maxlen:
            oldest = self._order.popleft()
            del self._facts[oldest]
        self._facts[fact.fact_id] = fact
        self._order.append(fact.fact_id)

    def get(self, fact_id: UUID) -> Fact | None:
        return self._facts.get(fact_id)

    def query(
        self,
        entity_id: str,
        since: Decimal | None = None,
        until: Decimal | None = None,
    ) -> tuple[Fact, ...]:
        result = []
        for fid in self._order:
            fact = self._facts[fid]
            if fact.entity_id != entity_id:
                continue
            if since is not None and fact.timestamp < since:
                continue
            if until is not None and fact.timestamp > until:
                continue
            result.append(fact)
        return tuple(result)


# --------------------------------------------------------------------------- #
# Tests auto-contenus (zéro dépendance de test externe)
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    from uuid import uuid4

    # --- Test 1 : commit() produit un FrozenContext correct ------------------
    class _TestClock:
        def __init__(self, value: Decimal) -> None:
            self._value = value

        def now(self) -> Decimal:
            return self._value

    clock = _TestClock(Decimal("1234.567"))
    entity_id = "user_42"
    causality = (uuid4(), uuid4())

    ctx = EvaluationContext(entity_id=entity_id, base_version=5)
    ctx.set("score", Decimal("0.85"))
    ctx.set("status", "flagged")
    ctx.set("count", 3)

    frozen = ctx.commit(causality=causality, clock=clock)

    assert frozen.entity_id == entity_id, "entity_id doit être conservé"
    assert frozen.version == 6, "version doit s'incrémenter depuis base_version"
    assert frozen.timestamp == Decimal("1234.567"), "timestamp doit venir du clock"
    assert frozen.causality == causality, "causality doit être passée tel quel"
    assert frozen.values["score"] == Decimal("0.85"), "valeurs doivent être préservées"
    assert frozen.values["status"] == "flagged"
    assert frozen.values["count"] == 3
    print("  ok commit() produit un FrozenContext correct")

    # --- Test 2 : MappingProxyType bloque la mutation externe ----------------
    try:
        frozen.values["score"] = Decimal("0.99")
        raise AssertionError("La mutation de frozen.values devrait lever TypeError")
    except TypeError:
        pass
    print("  ok mutation externe de frozen.values bloquée (TypeError)")

    # --- Test 3 : mutation post-commit de self._values n'affecte pas frozen -
    ctx.set("score", Decimal("0.10"))  # mutation après commit
    assert frozen.values["score"] == Decimal("0.85"), (
        "frozen ne doit pas être affecté par une mutation post-commit de _values"
    )
    print("  ok mutation post-commit de _values n'affecte pas le FrozenContext")

    # --- Test 4 : get() sur EvaluationContext --------------------------------
    assert ctx.get("score") == Decimal("0.10")
    assert ctx.get("missing") is None
    assert ctx.get("missing", "fallback") == "fallback"  # ajouté avec le fix
    print("  ok get() fonctionne, avec valeur par défaut")

    # --- Test 5 : InMemoryFactStore basique ----------------------------------
    store = InMemoryFactStore(max_facts=3)
    f1 = Fact(
        fact_id=uuid4(),
        entity_id="e1",
        fact_type="tx",
        _payload={"amount": 100},
        timestamp=Decimal("1.0"),
    )
    f2 = Fact(
        fact_id=uuid4(),
        entity_id="e1",
        fact_type="tx",
        _payload={"amount": 200},
        timestamp=Decimal("2.0"),
    )
    store.append(f1)
    store.append(f2)
    assert store.get(f1.fact_id) is f1
    assert len(store.query("e1")) == 2
    assert len(store.query("e1", since=Decimal("2.0"))) == 1
    print("  ok InMemoryFactStore basique")

    # --- Test 6 : FrozenContext explicitement non-hashable -------------------
    try:
        hash(frozen)
        raise AssertionError("FrozenContext ne devrait pas être hashable")
    except TypeError:
        pass
    print("  ok FrozenContext explicitement non-hashable (TypeError immédiat)")

    # --- Test 7 : ContextStore persiste et récupère par entité ---------------
    cstore = InMemoryContextStore()
    assert cstore.get_latest("user_42") is None
    cstore.save(frozen)
    retrieved = cstore.get_latest("user_42")
    assert retrieved is frozen
    assert cstore.get_latest("autre_entite") is None
    print("  ok ContextStore persiste et récupère par entité")

    print("\nTous les tests _context.py ont passé.")

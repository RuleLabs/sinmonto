from __future__ import annotations

import copy
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
            # deepcopy et non .copy() : une valeur imbriquée (liste, dict)
            # mutée en place après coup ne doit pas pouvoir corrompre
            # rétroactivement ce FrozenContext déjà figé. .copy() est
            # superficiel. Trouvé en revue croisée (Kimi, confirmé par
            # ChatGPT/Qwen/Grok) — 2026-08.
            values=MappingProxyType(copy.deepcopy(self._values)),
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
        if max_facts < 1:
            # deque(maxlen=0) fait planter le premier append() avec un
            # IndexError obscur (popleft sur deque vide) plutôt qu'un message
            # clair. Trouvé en revue (DeepSeek/Qwen) — 2026-08.
            raise ValueError("max_facts doit être >= 1")
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

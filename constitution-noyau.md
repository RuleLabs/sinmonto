# Constitution du noyau — spec technique complète

**Ce document remplace `constitution-noyau-v0.1.md`, `v0.2.md` et `v0.3.md` — ne plus les utiliser.** Les principes fondateurs vivent dans `constitution-finale.md`. Ce fichier est la spec technique complète et unique de ce que la v1.0 construit.

---

## 1. Objets fondamentaux

```python
class Clock(Protocol):
    def now(self) -> Decimal: ...

class ManualClock:
    """Pour les tests et le futur replay."""
    def set(self, value: Decimal) -> None: ...

@dataclass(frozen=True, slots=True)
class Fact:
    fact_id: UUID
    entity_id: str
    fact_type: str
    _payload: dict[str, Any]
    timestamp: Decimal
    causality: tuple[UUID, ...] = ()

    @property
    def payload(self) -> Mapping[str, Any]:
        return MappingProxyType(self._payload)   # vue réellement en lecture seule
                                                   # (TypeError à la mutation, O(1),
                                                   # zéro-copie) — pas juste un
                                                   # typage Mapping qui ne protège
                                                   # rien à l'exécution

@dataclass(frozen=True, slots=True)
class Signal:
    signal_id: UUID
    fact: Fact | None          # None pour un timer
    signal_type: str
    timestamp: Decimal

@dataclass(frozen=True, slots=True)
class Effect:
    effect_type: str
    payload: Mapping[str, Any]
    rule_id: str

class Evaluable(Protocol):
    rule_id: str
    priority: int
    def evaluate(self, ctx: EvaluationContext, fact: Fact | None) -> EvaluationResult: ...

@dataclass
class EvaluationResult:
    matched: bool
    effects: tuple[Effect, ...]
    derived_signals: tuple[Signal, ...]     # pas derived_facts — un fait dérivé est
                                             # encapsulé dans un Signal pour être
                                             # réinjecté ; la séparation Signal/Fact
                                             # tient jusqu'au bout
    context_delta: Mapping[str, Any]
    condition_results: Mapping[str, bool]

@dataclass(frozen=True, slots=True)
class Decision:
    signal_id: UUID
    entity_id: str
    effects: tuple[Effect, ...]
    trace: DecisionTrace
    context_version: int
    has_errors: bool = False
```

## 2. Context à deux phases

*(signature mise à jour — la version ci-dessous ne correspondait plus à
l'implémentation réelle de Kimi, trouvé par Meta IA en revue de clôture :
`_pending_effects` n'a jamais été utilisé, et `commit()` calcule la version
automatiquement plutôt que de la recevoir en paramètre)*

```python
class EvaluationContext:
    """Mutable. Vit uniquement pendant un appel à engine.evaluate()."""
    __slots__ = ('entity_id', '_base_version', '_values')

    def get(self, key: str, default: Any = None) -> Any: ...
    def set(self, key: str, value: Any) -> None: ...
    def commit(self, causality: tuple[UUID, ...], clock: Clock) -> "FrozenContext":
        """version = self._base_version + 1 (auto-calculée, pas reçue en
        paramètre) ; timestamp lu depuis clock.now(), jamais time.time()."""
        ...

@dataclass(frozen=True, slots=True)
class FrozenContext:
    """Un seul objet créé par cycle. Stocké, jamais modifié. Base du replay."""
    entity_id: str
    version: int
    values: Mapping[str, Any]
    causality: tuple[UUID, ...]
    timestamp: Decimal
```

## 3. Trace d'explication

```python
@dataclass(frozen=True, slots=True)
class ConditionTrace:
    kind: str                              # "field" | "and" | "or" | "not"
    description: str
    result: bool
    actual_value: Any = None               # rempli seulement pour kind == "field"
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
    evaluation_order: tuple[str, ...]      # ordre exact d'évaluation, audit du tie-break
```

Court-circuit par défaut sur les `AND` (les branches non évaluées n'apparaissent pas dans `children`) — performance avant exhaustivité de la trace en v1.0.

## 4. AlphaIndex

```python
class AlphaIndex:
    def index_rule(self, rule: Evaluable, condition: FieldCondition | CompositeCondition) -> None: ...
    def match(self, fact: Fact) -> set[str]:
        """Sur-ensemble de rule_id candidates. Ne garantit pas le match complet."""
        ...
    def optimize(self) -> None: ...   # appelé par engine.compile()
```

**Palier v1.0** : indexation par nom de champ référencé uniquement (peu importe AND/OR/NOT — un filtre par champ reste correct quelle que soit la structure booléenne, il ne fait qu'écarter les règles qui ne touchent à aucun champ du fait reçu). Les règles sans condition sur `Fact` (lisent uniquement `ctx`) vont dans un bucket `_unindexed`, toujours candidates.

**Palier différé (v1.1+, non codé maintenant)** : indexation par opérateur/valeur avec `bisect` pour les comparaisons de plage — vient se greffer derrière la même interface publique, sans rien casser côté appelant.

## 5. DSL

```python
class Field:
    __slots__ = ('name',)
    def __init__(self, name: str): self.name = name

    def __gt__(self, value): return FieldCondition(self.name, "gt", value)
    def __ge__(self, value): return FieldCondition(self.name, "gte", value)
    def __lt__(self, value): return FieldCondition(self.name, "lt", value)
    def __le__(self, value): return FieldCondition(self.name, "lte", value)
    def __eq__(self, value): return FieldCondition(self.name, "eq", value)
    def in_(self, values): return FieldCondition(self.name, "in", tuple(values))

@dataclass(frozen=True, slots=True)
class FieldCondition:
    field_name: str
    operator: str
    reference: Any
    def __and__(self, other): return CompositeCondition("and", (self, other))
    def __or__(self, other): return CompositeCondition("or", (self, other))
    def __invert__(self): return CompositeCondition("not", (self,))
    def evaluate(self, fact: Fact | None) -> ConditionTrace: ...

@dataclass(frozen=True, slots=True)
class CompositeCondition:
    kind: str
    children: tuple[FieldCondition | "CompositeCondition", ...]
    def __and__(self, other): return CompositeCondition("and", (self, other))
    def __or__(self, other): return CompositeCondition("or", (self, other))
    def evaluate(self, fact: Fact | None) -> ConditionTrace: ...
```

**Gotcha documenté** : `Field.__eq__` est détourné pour construire une `FieldCondition`. Deux `Field` ne sont plus comparables avec `==` au sens normal, et `Field` devient non hashable — assumé, même compromis que SQLAlchemy sur `Column`.

## 6. FactStore

```python
class FactStore(ABC):
    @abstractmethod
    def append(self, fact: Fact) -> None: ...
    @abstractmethod
    def get(self, fact_id: UUID) -> Fact | None: ...
    @abstractmethod
    def query(self, entity_id: str, since: Decimal | None = None,
              until: Decimal | None = None) -> tuple[Fact, ...]: ...

class InMemoryFactStore(FactStore):
    """Implémentation par défaut du cœur. Ring buffer, mémoire bornée par construction."""
    def __init__(self, max_facts: int = 100_000):
        self._facts: dict[UUID, Fact] = {}
        self._order: deque[UUID] = deque(maxlen=max_facts)

    def append(self, fact: Fact) -> None:
        if len(self._order) == self._order.maxlen:
            oldest = self._order.popleft()
            del self._facts[oldest]
        self._facts[fact.fact_id] = fact
        self._order.append(fact.fact_id)
```

Toute implémentation persistante (Redis, Postgres...) vit dans un adaptateur séparé, hors du cœur.

## 7. Exceptions

```python
class EngineError(Exception): ...

class EngineConfigurationError(EngineError): ...
class EngineNotCompiledError(EngineConfigurationError): ...
class EngineAlreadyCompiledError(EngineConfigurationError): ...
class DuplicateRuleError(EngineConfigurationError): ...
class InvalidConditionError(EngineConfigurationError): ...
class InvalidEffectError(EngineConfigurationError): ...

class EngineRuntimeError(EngineError): ...
class RuleEvaluationError(EngineRuntimeError):
    def __init__(self, rule_id: str, original: Exception, signal_id: UUID):
        self.rule_id = rule_id
        self.signal_id = signal_id
        super().__init__(f"Rule '{rule_id}' crashed on signal {signal_id}: {original}")
        self.__cause__ = original

class ContextCorruptionError(EngineRuntimeError): ...
class ClockError(EngineRuntimeError): ...
class BackendError(EngineError): ...   # adaptateurs de persistance, hors cœur
```

## 8. Sérialisation

```python
class _EngineJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal): return {"__type": "Decimal", "value": str(obj)}
        if isinstance(obj, UUID): return {"__type": "UUID", "value": str(obj)}
        if isinstance(obj, bytes): return {"__type": "bytes", "value": obj.decode("utf-8")}
        return super().default(obj)
```

`dataclasses.asdict()` + `json.dumps(..., cls=_EngineJSONEncoder)`. Jamais `pickle`. Aucune dépendance externe.

## 9. Tests — mini-runner interne (`_testing.py`, déjà complet, ~20 lignes)

```python
import traceback
from typing import Callable

def test(name: str, fn: Callable[[], None]) -> None:
    try:
        fn()
        print(f"  ok {name}")
    except AssertionError as e:
        print(f"  FAIL {name}: {e}")
    except Exception as e:
        print(f"  ERROR {name}: {type(e).__name__}: {e}")
        traceback.print_exc()

def assert_eq(actual, expected, msg=""):
    if actual != expected:
        raise AssertionError(f"{msg}\nExpected: {expected}\nActual: {actual}")
```

## 10. Le cycle d'évaluation

```
1. Signal entrant
2. Fact stocké dans le FactStore (append-only, indexé par entity+temps)
3. AlphaIndex.match(fact) -> ensemble des rule_id candidates
4. Chargement du dernier FrozenContext de l'entité -> EvaluationContext mutable
5. Évaluation des règles candidates, triées par priorité (tri stable Python =
   tie-break par ordre d'insertion), effets et deltas collectés
6. Erreur dans une règle -> capturée selon rule_error_policy (continue par défaut :
   isolée, tracée, context_delta jamais appliqué partiellement) ; jamais silencieuse
7. Signaux dérivés (EvaluationResult.derived_signals) -> mis en FILE D'ATTENTE,
   jamais réinjectés dans le même passage. max_derived_depth = 3 par défaut.
8. ctx.commit() -> un seul FrozenContext, stocké
9. Decision assemblée (effects + trace + context_version + has_errors) et retournée
10. File d'attente traitée après la fin du cycle courant, jusqu'à épuisement ou
    max_derived_depth atteint
```

## 11. Disposition des fichiers

*(voir `constitution-finale.md` §8 pour le principe verrouillé — seul `sinmonto.Symbole` est un chemin d'import garanti ; tous les fichiers internes sont préfixés `_`, sans exception)*

```
sinmonto/
├── __init__.py       # seul chemin d'import public garanti, exports via __all__
├── _version.py
├── _exceptions.py    # racine du graphe de dépendances internes (§7) — n'importe
│                      # rien d'autre en interne, pour éviter les imports circulaires
├── _core.py           # Clock, Fact, Signal, Effect, Decision, EvaluationResult (§1),
│                       # sérialisation (§8)
├── _context.py         # EvaluationContext, FrozenContext, FactStore, InMemoryFactStore
├── _engine.py          # AlphaIndex, Evaluable, Rule, DecisionEngine
├── _dsl.py             # Field, FieldCondition, CompositeCondition, décorateur @rule
├── _trace.py           # ConditionTrace, RuleTrace, DecisionTrace
└── _testing.py         # mini-runner (§9 — déjà écrit, à copier tel quel)
```

## 12. Roadmap

**Fait, intégré, testé de bout en bout** (`_core.py`, `_context.py`, `_dsl.py`, `_engine.py`, `_trace.py`, `_exceptions.py`, `_testing.py` — un scénario réel avec `@rule`, deux règles, une décision expliquée par sa trace, tourne sans erreur).

**Priorité immédiate — trouvé en faisant tourner le code, pas prévu à l'avance :**

| # | Manque | Pourquoi c'est bloquant |
|---|---|---|
| 1 | Persistance du contexte entre deux appels à `evaluate()` — aucun `ContextStore`, `EvaluationContext` repart de zéro à chaque cycle | Bloquant pour tout usage réel : impossible de compter "3 transactions en 5 minutes" si l'état ne survit pas d'un appel à l'autre |
| 2 | File d'attente des signaux dérivés (`max_derived_depth`) — un signal dérivé produit aujourd'hui est perdu | Bloquant pour les cascades (alerte → scoring → blocage) |
| 3 | `duration_ms` figé à `Decimal("0")` | Non bloquant, juste pas mesuré |
| 4 | AND chaînés imbriqués plutôt qu'aplatis dans la trace | Cosmétique, lisibilité de l'explicabilité |

Proposition d'interface pour le #1, mêmes conventions que `FactStore` :
```python
class ContextStore(ABC):
    @abstractmethod
    def get_latest(self, entity_id: str) -> FrozenContext | None: ...
    @abstractmethod
    def save(self, frozen: FrozenContext) -> None: ...

class InMemoryContextStore(ContextStore):
    def __init__(self) -> None:
        self._latest: dict[str, FrozenContext] = {}
    def get_latest(self, entity_id: str) -> FrozenContext | None:
        return self._latest.get(entity_id)
    def save(self, frozen: FrozenContext) -> None:
        self._latest[frozen.entity_id] = frozen
```

**Phase suivante (confirmée, inchangée)** :

| Étape | Contenu | Durée réaliste |
|---|---|---|
| 3 | Fenêtres (`deque` + agrégats naïfs) | 2-3 jours |
| 4 | Transitions d'état comme `Evaluable` spécialisé | 1-2 jours |
| 5 | `engine.replay()` sur le `FactStore` déjà en place | 1-2 jours |

**Plus tard, pas urgent** : benchmark de charge (1000 règles, 10000 faits — proposé par Kimi lors d'une revue précédente), packaging réel (`pyproject.toml`, `pip install -e .`).

## 13. Statut

Spec complète. Plus aucune question ouverte — Q1 à Q6 verrouillées, l'incohérence entre elles résolue, les angles morts comblés. Prêt pour le premier tour d'implémentation réel.

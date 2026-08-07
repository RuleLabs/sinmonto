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
    entity_id: str | None = None
    # Dérivé de fact.entity_id si non fourni et qu'un fact est présent.
    # Obligatoire explicitement si fact est None (timer) — sinon aucun
    # moyen de savoir à quelle entité le signal se rapporte. Si les deux
    # sont fournis et diffèrent : ValueError (évite une évaluation sous
    # une entité pendant que le Fact reste stocké sous une autre — trouvé
    # en revue croisée, 2026-08). Champ absent de cette section jusqu'ici
    # bien que déjà implémenté — corrigé.

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
    condition_trace: ConditionTrace | None  # l'arbre réel produit par condition.evaluate(),
                                             # pas un condition_results plat — corrigé en
                                             # intégration, cette section disait encore
                                             # l'ancien champ

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
        paramètre) ; timestamp lu depuis clock.now(), jamais time.time().
        Isolation par copy.deepcopy (pas .copy()/dict() superficiel) — une
        valeur imbriquée mutée après coup, ou au rechargement du contexte
        précédent au cycle suivant, ne doit pas corrompre rétroactivement
        un FrozenContext déjà figé. Snapshot/restore autour de chaque
        rule.evaluate() dans le moteur pour la même raison, côté mutation
        directe (ctx.set() dans une action). Trouvé en revue croisée
        (Kimi, ChatGPT, Qwen, Grok, Meta AI) — 2026-08."""
        ...

@dataclass(frozen=True, slots=True)
class FrozenContext:
    """Un seul objet créé par cycle. Stocké, jamais modifié. Base du replay."""
    entity_id: str
    version: int
    values: Mapping[str, Any]
    causality: tuple[UUID, ...]   # (fact.fact_id, *fact.causality) pour un fait,
                                   # (signal.signal_id,) pour un timer — avant :
                                   # fact.causality seul, ou () pour un timer,
                                   # perdait l'origine immédiate dans les deux cas.
                                   # Verrouillé en revue croisée — 2026-08.
    timestamp: Decimal
```

## 3. Trace d'explication

```python
@dataclass(frozen=True, slots=True)
class ConditionTrace:
    kind: str                              # "field" | "and" | "or" | "not" | "none" | "error"
                                            # "none" : règle sans condition (toujours vraie).
                                            # "error" : règle qui a levé une exception —
                                            # les deux déjà produits par le moteur, absents
                                            # d'ici jusqu'à cette correction (revue croisée,
                                            # 2026-08).
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
    def index_rule(self, rule_id: str, condition: FieldCondition | CompositeCondition | None) -> None: ...
    # Signature réelle : rule_id (str), pas rule (Evaluable) — plus flexible,
    # découple l'index de l'objet Rule complet. condition accepte None (règle
    # sans condition sur Fact, va dans _unindexed). Cette section montrait
    # encore l'ancienne signature — corrigé, 2026-08.
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

**Validation à la construction (2026-08)** : `FieldCondition.__post_init__` rejette un `operator` inconnu (`InvalidConditionError`), `CompositeCondition.__post_init__` rejette un `kind` inconnu — au moment le plus tôt possible, avant même `add_rule()`/`compile()`. Avant : un opérateur mal orthographié (ex. `"gtt"`) évaluait silencieusement `False` pour toujours, sans jamais rien lever — contraire à "fail loud". Trouvé en revue croisée (ChatGPT, Qwen, Kimi).

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
        if max_facts < 1:
            raise ValueError("max_facts doit être >= 1")
            # deque(maxlen=0) faisait planter le premier append() avec un
            # IndexError obscur plutôt qu'un message clair — trouvé en revue
            # croisée (DeepSeek, Qwen), 2026-08.
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
# InvalidEffectError était définie mais jamais levée jusqu'ici. Activée
# 2026-08 : Rule.evaluate() la lève quand une action retourne un type non
# reconnu (silencieusement ignoré avant), ou retourne un EvaluationResult
# directement (interdit — court-circuiterait le condition_trace déjà
# calculé par la règle). Levée pendant evaluate(), pas à add_rule() — la
# forme d'un retour d'action ne se connaît qu'en l'exécutant — mais reste
# une sous-classe d'EngineConfigurationError par cohérence de nommage ;
# capturée comme n'importe quelle exception de règle par le moteur
# (gouvernée par rule_error_policy). Trouvé en revue croisée (ChatGPT,
# Qwen).

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

**Ajout 2026-08** : `test()` compte les échecs (`_failure_count`) et un handler `atexit` termine le process avec un code de sortie non nul si au moins un test a échoué — un run avec des `FAIL`/`ERROR` sortait avant avec le code 0, invisible pour un script CI. Détail d'implémentation qui a son importance : `sys.exit()` depuis un callback `atexit` est explicitement avalé par Python (« Exception ignored in atexit callback », vérifié en le testant) ; `os._exit()` après un `flush()` explicite des flux est nécessaire pour que le code de sortie soit réellement pris en compte par le process appelant. Trouvé en revue croisée (DeepSeek, Qwen).

## 10. Le cycle d'évaluation

```
1. Signal entrant
2. Fact stocké dans le FactStore (append-only, indexé par entity+temps)
3. AlphaIndex.match(fact) -> ensemble des rule_id candidates
4. Chargement du dernier FrozenContext de l'entité -> EvaluationContext mutable
5. Évaluation des règles candidates, triées par priorité (tri stable Python =
   tie-break par ordre d'insertion), effets et deltas collectés
6. Erreur dans une règle -> capturée selon rule_error_policy (continue par défaut :
   isolée, tracée, context_delta jamais appliqué partiellement — y compris une
   mutation faite directement via ctx.set() dans l'action, pas seulement le
   context_delta retourné : snapshot de ctx pris avant chaque règle, restauré si
   elle plante, 2026-08) ; jamais silencieuse. except Exception uniquement — pas
   BaseException, SystemExit/KeyboardInterrupt remontent et interrompent
   l'évaluation (constitution-finale.md Q3).
7. Signaux dérivés (EvaluationResult.derived_signals) -> mis en FILE D'ATTENTE,
   jamais réinjectés dans le même passage. max_derived_depth = 3 par défaut.
8. ctx.commit() -> un seul FrozenContext, stocké. causality = (fact.fact_id,
   *fact.causality) pour un fait, (signal.signal_id,) pour un timer (2026-08 —
   avant : fact.causality seul, ou () pour un timer).
9. Decision assemblée (effects + trace + context_version + has_errors) et retournée
10. File d'attente traitée après la fin du cycle courant, jusqu'à épuisement ou
    max_derived_depth atteint
```

## 11. Disposition des fichiers

*(voir `constitution-finale.md` §8 pour le principe verrouillé — les 37 noms de `sinmonto.__all__` sont le chemin d'import garanti, pas un symbole unique ; tous les fichiers internes sont préfixés `_`, sans exception)*

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

**Fait, intégré, testé de bout en bout** (`_core.py`, `_context.py`, `_dsl.py`, `_engine.py`, `_trace.py`, `_exceptions.py`, `_testing.py` — un scénario réel avec `@rule`, deux règles, une décision expliquée par sa trace, tourne sans erreur). `ContextStore`/`InMemoryContextStore` (ci-dessous) : implémentés et câblés dans `_engine.py` depuis la correction d'intégration listée en tête de `_engine.py` — cette section les décrivait encore comme "priorité immédiate #1" alors qu'ils étaient déjà faits ; corrigé, 2026-08.

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

**0.1.0-preview (2026-08) — bugs silencieux bloquants corrigés en revue croisée multi-IA** (ChatGPT, Grok, DeepSeek, Kimi, Qwen, Meta AI) : copie profonde du contexte (commit + rechargement), snapshot/restore autour de chaque règle (atomicité réelle, y compris mutation directe de `ctx`), `Signal.entity_id` validé contre `fact.entity_id`, opérateur/kind de condition invalide rejeté à la construction, retour d'action non reconnu levé plutôt qu'ignoré, copie défensive de `Fact._payload`, `causality` chaînée, contrat `Symbole` remplacé par la surface `__all__` réelle. Détail par bug : voir `journal-integration.md`.

**Reste ouvert, assumé pour la preview — pas prévu à l'avance, documenté honnêtement :**

| # | Manque | Pourquoi c'est non bloquant pour une preview |
|---|---|---|
| 1 | File d'attente des signaux dérivés (`max_derived_depth`) — un signal dérivé produit aujourd'hui est perdu | Décision d'architecture (récursif ? tick() séparé ?) qui mérite son propre tour dédié, pas une correction en urgence |
| 2 | `duration_ms` figé à `Decimal("0")` | Non bloquant, juste pas mesuré |
| 3 | AND chaînés imbriqués plutôt qu'aplatis dans la trace | Cosmétique, lisibilité de l'explicabilité |
| 4 | Pas de politique de rétention sur `InMemoryContextStore`/`InMemoryFactStore` | Stores mémoire, usage prévu = tests/démo/prototype, pas production long-terme |

**Phase suivante (confirmée, inchangée)** :

| Étape | Contenu | Durée réaliste |
|---|---|---|
| 3 | Fenêtres (`deque` + agrégats naïfs) | 2-3 jours |
| 4 | Transitions d'état comme `Evaluable` spécialisé | 1-2 jours |
| 5 | `engine.replay()` sur le `FactStore` déjà en place | 1-2 jours |

**Plus tard, pas urgent** : benchmark de charge (1000 règles, 10000 faits — proposé par Kimi lors d'une revue précédente), packaging réel (`pyproject.toml`, `pip install -e .`).

## 13. Statut

Spec complète. Plus aucune question ouverte — Q1 à Q6 verrouillées, l'incohérence entre elles résolue, les angles morts comblés. Prêt pour le premier tour d'implémentation réel.

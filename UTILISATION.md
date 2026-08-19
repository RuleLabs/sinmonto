# UTILISATION.md — écrire du code qui *utilise* sinmonto

**Pour qui** : toute IA (ou humain) qui doit produire du code applicatif
consommant `sinmonto` comme bibliothèque — pas modifier le noyau.

**Pas ce fichier** : si tu modifies `sinmonto/` lui-même, lis `AGENTS.md`
et `CLAUDE.md` à la place.

**Version documentée** : `0.1.0rc3` (preview). Vérifie `sinmonto.__version__` — ce document peut prendre du retard sur une version plus récente.

---

## 1. En une phrase

Moteur de décision événementiel, explicable, zéro dépendance : un `Signal`
entre, des règles déclaratives matchent, une `Decision` sort avec ses
`Effect` (données, pas d’effets de bord) et une trace complète.

## 2. Import — surface publique uniquement

```python
from sinmonto import (
    DecisionEngine,
    Fact,
    Signal,
    Effect,
    Field,
    rule,
    ManualClock,
    # lecture de résultats
    Decision,
    ConditionTrace,
    RuleTrace,
    DecisionTrace,
    # erreurs utiles à attraper
    EngineNotCompiledError,
    EngineAlreadyCompiledError,
    DuplicateRuleError,
    InvalidConditionError,
    InvalidEffectError,
    RuleEvaluationError,
)
```

**Règle** : n’importe **jamais** `sinmonto._engine`, `sinmonto._dsl`, etc.
Seul `from sinmonto import …` est un contrat stable. Tout fichier préfixé
`_` est interne et peut changer sans préavis.

La liste complète des symboles publics est `sinmonto.__all__`.

## 3. Modèle mental (5 objets)

| Objet | Rôle |
|-------|------|
| `Fact` | Information immuable (`entity_id`, `fact_type`, `payload`, `timestamp`) |
| `Signal` | Déclencheur d’un cycle (`fact` optionnel pour un timer, `entity_id` obligatoire) |
| `Effect` | Effet de bord **décrit**, jamais exécuté par le moteur |
| `EvaluationContext` / `FrozenContext` | État mutable pendant le cycle, figé à la fin, **persisté par entité** |
| `Decision` | Sortie : `effects` + `trace` + `context_version` + `has_errors` |

Le moteur **ne** fait **pas** d’appel réseau, d’écriture base, ni de log métier.
Toi (ou un exécuteur séparé) appliques les `Effect` après coup.

## 4. Recette canonique

```python
from decimal import Decimal
from uuid import uuid4
from sinmonto import DecisionEngine, Fact, Signal, Effect, Field, rule, ManualClock

clock = ManualClock(Decimal("0"))  # en prod : injecter une Clock réelle
engine = DecisionEngine(clock=clock)

@rule(
    name="high_amount_alert",
    priority=100,
    condition=(Field("amount") > 1000) & (Field("vip") == False),
    engine=engine,
)
def check_high_amount(ctx, fact):
    # Lire le contexte persistant
    visits = ctx.get("visits", 0)
    return [
        Effect("FLAG_TRANSACTION", {"reason": "high_amount_non_vip"}, "high_amount_alert"),
        {"risk_score": 0.85, "visits": visits + 1},  # delta de contexte
    ]

engine.compile()  # obligatoire avant evaluate ; plus d'add_rule après

fact = Fact(
    fact_id=uuid4(),
    entity_id="usr_99",
    fact_type="payment",
    _payload={"amount": 2500, "vip": False},
    timestamp=clock.now(),
)
signal = Signal(
    signal_id=uuid4(),
    fact=fact,
    signal_type="payment_received",
    timestamp=clock.now(),
    # entity_id omis → dérivé de fact.entity_id
)

decision = engine.evaluate(signal)

# Appliquer les effets (ton code, pas le moteur)
for effect in decision.effects:
    print(effect.effect_type, dict(effect.payload))

# Lire la preuve
for rt in decision.trace.rule_traces:
    print(rt.rule_id, "matched=" + str(rt.matched), rt.condition_tree.description)
```

Sans décorateur, équivalent :

```python
from sinmonto import Rule, Field, Effect

engine.add_rule(Rule(
    rule_id="high_amount_alert",
    priority=100,
    condition=(Field("amount") > 1000) & (Field("vip") == False),
    action=check_high_amount,
))
engine.compile()
```

## 5. Écrire une action de règle — contrat strict

Signature : `def action(ctx, fact) -> …`

### Retours acceptés

| Retour | Effet |
|--------|--------|
| `Effect(...)` | un effet |
| `Signal(...)` | signal dérivé (**accepté mais non traité en v0.1** — perdu) |
| `dict` | fusionné dans le contexte (`context_delta`) |
| `list` / `tuple` de `Effect`, `Signal`, et/ou `dict` | combinaison |
| `None` | match sans effet ni delta |
| `EvaluationResult` (retour direct) | **interdit** — lève `InvalidEffectError` (écraserait le `condition_trace` déjà calculé par la règle) |
| tout le reste (`int`, `str`, objet non listé…) | lève `InvalidEffectError`, pas de silence |

```python
# Bon
return Effect("BLOCK", {"reason": "velocity"}, "velocity_check")

# Bon — effet + état
return [
    Effect("FLAG", {"code": "R1"}, "r1"),
    {"strike_count": ctx.get("strike_count", 0) + 1},
]

# Bon — lecture seule du contexte
score = ctx.get("risk_score", 0.0)
```

### Interdit / dangereux

```python
# MAUVAIS — effet de bord dans la règle
db.save(...)
requests.post(...)

# À ÉVITER — muter ctx directement plutôt que retourner un delta.
# Depuis rc2, un snapshot/restore protège contre la corruption si la règle
# plante ensuite (ctx.set() puis crash ne survit plus au commit final) —
# ce n'est donc plus un risque de corruption. Le vrai problème : ça sort
# du mécanisme de delta traçable. context_delta est construit depuis la
# VALEUR DE RETOUR de l'action, pas depuis l'état de ctx — un ctx.set()
# direct persiste (si la règle ne plante pas) mais n'apparaît nulle part
# dans context_delta, donc pas dans un audit qui s'appuie dessus.
ctx.set("x", 1)

# BON — retourner le delta ; visible dans context_delta, donc auditable
return {"x": 1}
```

**Règle d’or** : une action décrit des `Effect` et des deltas ; elle n’exécute rien.

### Conditions (`Field`)

```python
Field("amount") > 1000
Field("amount") >= 1000
Field("status") == "open"
Field("status") != "closed"
Field("country").in_(("BJ", "TG", "CI"))
(Field("amount") > 1000) & (Field("vip") == False)
(Field("amount") > 5000) | (Field("risk") == "high")
~(Field("test") == True)
```

- Les conditions portent sur le **payload du `Fact`**, pas sur le contexte.
- Champ absent ou `fact is None` → condition fausse (pas d’exception).
- `Field.__eq__` construit une condition : deux `Field` ne sont pas comparables
  comme des objets Python normaux ; `Field` n’est pas hashable.

### Priorité et ordre

- Priorité plus haute d’abord (`priority=100` avant `priority=10`).
- À priorité égale : **ordre d’enregistrement** (déterministe).
- `decision.trace.evaluation_order` enregistre l’ordre exact du cycle.

## 6. Signal, Fact, entity_id

```python
# Cas normal — entity_id dérivé du fact
fact = Fact(fact_id=uuid4(), entity_id="usr_1", fact_type="tx",
            _payload={"amount": 10}, timestamp=clock.now())
signal = Signal(signal_id=uuid4(), fact=fact, signal_type="tx",
                timestamp=clock.now())

# Timer — pas de fact → entity_id obligatoire
signal = Signal(
    signal_id=uuid4(),
    fact=None,
    signal_type="daily_tick",
    timestamp=clock.now(),
    entity_id="usr_1",
)
```

Le contexte est **par `entity_id`** : deux signaux pour `"usr_1"` partagent
le même état cumulé ; `"usr_2"` a le sien.

## 7. Lire une Decision

```python
decision.effects          # tuple[Effect, ...]
decision.has_errors       # True si au moins une règle a planté (policy continue)
decision.context_version  # version du FrozenContext après ce cycle
decision.trace.evaluation_order
decision.trace.rule_traces  # une RuleTrace par règle évaluée

rt = decision.trace.rule_traces[0]
rt.matched
rt.condition_tree.kind         # "field" | "and" | "or" | "not" | "error" | "none"
rt.condition_tree.result
rt.condition_tree.actual_value # pour kind == "field"
rt.condition_tree.children     # sous-arbre (court-circuit : branches non évaluées absentes)
```

## 8. Gestion d’erreur (côté moteur)

À la compilation : fail loud (doublon de `rule_id`, condition mal typée, etc.).

À l’exécution, politique par défaut `"continue"` :

- exception dans une règle → capturée, `has_errors=True`, autres règles continuent ;
- le `context_delta` **retourné** par une règle qui plante n’est pas appliqué.

Forcer un autre mode (usage avancé / tests) :

```python
engine._config["rule_error_policy"] = "fail_fast"  # ou "fail_loud"
```

(`EngineConfig` public n’existe pas encore en v0.1 — `_config` est interne.)

## 9. Horloge

```python
from sinmonto import ManualClock
from decimal import Decimal

clock = ManualClock(Decimal("1700000000"))
clock.now()   # Decimal
clock.set(Decimal("1700000001"))
```

Ne jamais appeler `time.time()` dans une règle. Pour les tests et le futur
replay, injecter `ManualClock`. En production, passer une `Clock` dont
`now()` renvoie un `Decimal`.

## 10. Limitations v0.1 — ne pas inventer ces APIs

| Sujet | État réel |
|-------|-----------|
| Signaux dérivés (`EvaluationResult.derived_signals`) | Acceptés par l’API, **non traités** (pas de cascade) |
| `RuleTrace.duration_ms` | Toujours `Decimal("0")` |
| Fenêtres temporelles / agrégats | Non |
| Transitions d’état (FSM) | Non |
| `engine.replay()` | Non |
| Exécuteur d’`Effect` | Non fourni — à écrire côté appli |
| Rétention / borne des stores mémoire | Ring buffer sur les faits seulement (`max_facts`) |

Si tu as besoin d’une cascade (alerte → score → blocage), enchaîne **toi-même**
plusieurs `evaluate()` côté applicatif pour l’instant, ou attends la file
dérivée (roadmap).

## 11. Checklist anti-patterns (à appliquer avant de livrer du code)

- [ ] Imports uniquement depuis `sinmonto`, jamais `sinmonto._*`
- [ ] `engine.compile()` appelé une fois après toutes les règles
- [ ] Aucun I/O dans le corps d’une action (pas de réseau, disque, DB)
- [ ] État écrit via `return {"clé": valeur}`, pas `ctx.set(...)` en production
- [ ] `Effect.rule_id` cohérent avec le `name` / `rule_id` de la règle
- [ ] `entity_id` stable et explicite pour les timers
- [ ] Pas d’assumption sur le traitement des signaux dérivés
- [ ] Pas d’assumption sur `duration_ms > 0`
- [ ] Les `Effect` sont appliqués **après** `evaluate()`, par ton code

## 12. Exemple minimal testable

```python
from decimal import Decimal
from uuid import uuid4
from sinmonto import DecisionEngine, Fact, Signal, Effect, Field, rule

engine = DecisionEngine()

@rule(name="gt100", priority=10, condition=Field("amount") > 100, engine=engine)
def flag(ctx, fact):
    return Effect("ALERT", {"amount": fact.payload["amount"]}, "gt100")

engine.compile()

fact = Fact(
    fact_id=uuid4(), entity_id="e1", fact_type="tx",
    _payload={"amount": 150}, timestamp=Decimal("0"),
)
decision = engine.evaluate(Signal(
    signal_id=uuid4(), fact=fact, signal_type="tx", timestamp=Decimal("0"),
))
assert len(decision.effects) == 1
assert decision.effects[0].effect_type == "ALERT"
assert decision.trace.rule_traces[0].matched is True
```

## 13. Où aller ensuite

| Besoin | Fichier |
|--------|---------|
| Contribuer au noyau | `AGENTS.md`, `CLAUDE.md` |
| Pourquoi ces choix d’archi | `docs/constitution-finale.md` |
| Spec technique du noyau | `docs/constitution-noyau.md` |
| Ce qui n’est pas encore bâti | `docs/roadmap-vision.md` |
| Historique des bugs d’intégration | `docs/journal-integration.md` |
| Exemple exécutable du dépôt | `examples/end_to_end.py` |

---

*Ce fichier est le contrat d’usage pour le code généré par IA. S’il contredit
le code de `sinmonto/__init__.py`, le code prime — ouvre une entrée dans
`docs/journal-integration.md`.*

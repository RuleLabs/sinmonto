# sinmonto

Moteur de décision événementiel, explicable, en Python pur — zéro dépendance.

Du fon *Sɛ́n mɔto* ("moteur de règle"). Chaque décision porte sa propre preuve : pourquoi une règle a matché, pourquoi une autre non, dans quel ordre, avec quelles valeurs réelles au moment de l'évaluation.

**Statut : `0.1.0rc2` — preview technique.** Le noyau est testé (41 tests, modules + intégration bout-en-bout) et les bugs silencieux trouvés en revue croisée multi-IA sont corrigés (voir « Limitations connues » plus bas pour ce qui reste volontairement ouvert). Reste en pre-release le temps d'un premier retour d'usage externe réel — l'API 0.x n'est pas encore figée.

## Pourquoi

- **Zéro dépendance** — s'installe et s'audite n'importe où, sans arbre de dépendances à faire valider par une équipe sécurité.
- **Explicabilité native** — chaque décision produit un arbre de traçage complet, pas un log ajouté après coup.
- **Effects-as-data** — une règle ne fait jamais d'appel réseau ni d'écriture en base. Elle décrit un `Effect`. Un exécuteur séparé l'applique. Ça rend le moteur testable et rejouable par construction.
- **État persistant par entité** — un `ContextStore` garde la mémoire d'une entité (utilisateur, appareil, transaction) d'un événement à l'autre, sans quoi aucun comptage ou score cumulé n'est possible.
- **Déterministe** — mêmes entrées, même ordre d'enregistrement des règles ⇒ même sortie, bit à bit, y compris en cas d'égalité de priorité.

## Installation

```bash
pip install sinmonto
```

*(Package en préparation — voir `pyproject.toml`. Pour l'instant, `pip install -e .` depuis une copie locale du dépôt. Une fois publié : la version étant une pre-release (`0.1.0rc2`), `pip install sinmonto` seul ne l'installera pas — il faudra `pip install --pre sinmonto`, cohérent avec le statut preview ci-dessus.)*

## Exemple

```python
from decimal import Decimal
from uuid import uuid4

from sinmonto import DecisionEngine, Effect, Fact, Field, Signal, rule

engine = DecisionEngine()

@rule(name="high_amount_alert", priority=100,
      condition=(Field("amount") > 1000) & (Field("vip") == False),
      engine=engine)
def check_high_amount(ctx, fact):
    return Effect("FLAG_TRANSACTION", {"reason": "high_amount_non_vip"}, "high_amount_alert")

engine.compile()

fact = Fact(fact_id=uuid4(), entity_id="usr_99", fact_type="payment",
            _payload={"amount": 2500, "vip": False}, timestamp=Decimal("0"))
signal = Signal(signal_id=uuid4(), fact=fact, signal_type="payment_received", timestamp=Decimal("0"))

decision = engine.evaluate(signal)

print(decision.effects)
# (Effect(effect_type='FLAG_TRANSACTION', payload={'reason': 'high_amount_non_vip'}, rule_id='high_amount_alert'),)

trace = decision.trace.rule_traces[0]
print(trace.condition_tree.description, "->", trace.condition_tree.result)
# amount gt 1000 -> True
```

Un deuxième signal pour `usr_99` reprend automatiquement le contexte du premier — voir [`examples/end_to_end.py`](./examples/end_to_end.py) et le `ContextStore`.

## Statut de la revue croisée (2026-08)

Le dépôt est passé par une revue de code croisée multi-IA (ChatGPT, Grok, DeepSeek, Kimi, Qwen, Meta AI). Six bugs silencieux — ceux qui trahissaient la promesse d'explicabilité/déterminisme plutôt que de simples trous documentés — ont été corrigés avant cette preview : copie profonde du contexte, atomicité réelle des règles (snapshot/restore, y compris mutation directe de `ctx`), validation `Signal.entity_id`/opérateurs de condition/retours d'action, copie défensive du payload, `causality` chaînée. Détail complet, bug par bug : [`journal-integration.md`](./journal-integration.md).

## Limitations connues (v0.1.0-preview) — assumées, pas des bugs

- Les signaux dérivés (`EvaluationResult.derived_signals`) sont acceptés par l'API mais **non traités** — pas de cascade de règles dans cette version. Décision d'architecture (file séparée ? récursif ?) reportée à un tour dédié plutôt que corrigée en urgence. Prévu en v0.2.0.
- `RuleTrace.duration_ms` est toujours `Decimal("0")` — pas de mesure réelle du temps d'exécution.
- AND chaînés imbriqués plutôt qu'aplatis dans la trace — cosmétique, la logique et le court-circuit restent corrects.
- Pas de politique de rétention sur `InMemoryContextStore`/`InMemoryFactStore` — stores mémoire pensés pour tests/démo/prototype, pas pour une production longue durée sans adaptateur dédié.
- Pas encore de fenêtres temporelles, de transitions d'état (FSM), ni de `engine.replay()` — voir `roadmap-vision.md`.

## Architecture et gouvernance

Ce projet est construit avec une discipline de documentation stricte, en revue croisée avec plusieurs IA :

- [`constitution-finale.md`](./constitution-finale.md) — principes architecturaux verrouillés, stables à travers toutes les versions.
- [`constitution-noyau.md`](./constitution-noyau.md) — spécification technique complète de ce que le noyau construit.
- [`journal-integration.md`](./journal-integration.md) — historique honnête : ce qui a été tenté, les bugs trouvés, comment ils ont été corrigés.
- [`roadmap-vision.md`](./roadmap-vision.md) — ce qui n'est pas encore construit, et pourquoi ce n'est pas encore le moment.

## Licence

Apache License 2.0 — voir [`LICENSE`](./LICENSE).

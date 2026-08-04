# Constitution finale

Ce document est distinct de la Constitution du noyau (`constitution-noyau-v0.X.md`, qui décrit la v1.0 du *logiciel*). Celui-ci contient les principes fondateurs, censés rester stables à travers toutes les versions futures — pas une liste de fonctionnalités. Comme une vraie constitution : peu d'articles, rarement modifiés, gouvernant *comment* les décisions se prennent et *quelles conventions* tiennent dans le temps — pas ce que chaque version contient.

**Numérotation** : ce document a sa propre édition, indépendante des versions du logiciel (noyau v1.0, v1.1...). Édition 1.

---

## 1. Positionnement

Le moteur de décision embarquable — zéro infrastructure, zéro dépendance, auditable ligne par ligne. Rivalise sur l'ergonomie, l'auditabilité et le zéro-infra, pas sur la performance brute contre des moteurs JVM/Rust.

## 2. Les 10 décisions architecturales verrouillées

1. Pas de réseau Rete complet — indexation alpha légère uniquement.
2. `Context` mutable pendant un cycle d'évaluation, figé en `FrozenContext` immuable à la fin (`commit()`) — jamais d'immuabilité totale à la façon persistante.
3. `Signal` (déclencheur) et `Fact` (information) sont deux types distincts.
4. Effects-as-data : aucune règle n'exécute d'effet de bord. Elle retourne des `Effect` décrits ; un exécuteur séparé les applique.
5. Explicabilité native dans le moteur de matching, jamais ajoutée après coup — chaque condition, vraie ou fausse, doit être traçable.
6. Pas de durabilité multi-jours dans le cœur (pas de BPM/workflow complet). Un `StateBackend` abstrait, implémentations concrètes hors du cœur.
7. Temps injecté (`Clock`), jamais `time.time()` appelé directement dans le moteur.
8. `engine.compile()` verrouille la configuration ; après compilation, plus aucune règle ne peut être ajoutée sans recompiler.
9. `__slots__` sur les objets internes chauds (`Fact`, `Signal`, `Effect`, `Decision`, `Trace`) — jamais sur le `payload` utilisateur, qui reste un `dict` libre.
10. Type d'implémentation : protocole commun `Evaluable`, classes distinctes (`Rule`, `Transition`...) qui l'implémentent — pas un type générique fourre-tout.

*Source canonique. Le gabarit du contrat vivant en copie le texte pour l'envoi aux autres IA — si ce document change, la copie doit être mise à jour.*

## 3. Philosophie d'organisation — vaut pour toutes les versions futures

- **Cœur + adaptateurs** : le cœur reste zéro dépendance. Toute extension (persistance, accélération native, MCP, plateforme) vit dans un package séparé.
- **Interface verrouillée, implémentation différée** : chaque interface publique (`AlphaIndex`, `FactStore`, `StateBackend`...) peut avoir une implémentation naïve maintenant et une implémentation plus sophistiquée plus tard, sans jamais changer le contrat dont dépendent les autres modules.
- **Stabilité API en deux couches** : `[package].api.*` sous SemVer strict ; `[package]._internal.*` libre de changer entre versions mineures.

## 4. Processus de gouvernance — le filtre v1.0

À chaque décision : *"est-ce que ça rapproche réellement la version en cours de construction, ou est-ce qu'on rêve d'une fonctionnalité qui n'a peut-être jamais besoin d'exister maintenant ?"* Si c'est la seconde réponse, ça va dans `roadmap-vision.md`, jamais dans une Constitution.

## 5. Processus de gouvernance — le contrat vivant

Toute évolution de ce document ou de la Constitution du noyau passe par le gabarit `contrat-vivant-gabarit.md` : mission envoyée à chaque IA participante, rapports structurés en retour, synthèse commune avant verrouillage. Aucune décision constitutionnelle n'est prise unilatéralement par une seule IA — celle-ci y compris.

## 6. Hygiène du projet

- **Licence** : MIT ou Apache-2.0 — à trancher avant la première release publique, sans urgence technique.
- **Version Python plancher** : 3.11+.
- **Tests** : `assert` + blocs `if __name__ == "__main__":`, zéro dépendance de test tant que la surface ne justifie pas `pytest`.
- **Nom du package** : `sinmonto` — verrouillé. Du fon *Sɛ́n mɔto* ("moteur de règle"), traduction officielle et grammaticalement correcte, pas un mot inventé. Vérifié sans collision commerciale ou logicielle notable.

## 7. Compléments verrouillés (ratifiés après consultation multi-IA — DeepSeek pro, DeepSeek, Kimi, ChatGPT, Grok, Gemini)

**Q1 — Conventions de nommage du code**
PEP8 strict. Structure : `[package]/api/` (surface publique, exports explicites via `__all__` pour étanchéifier le contrat SemVer) + `[package]/_internal/` (privé, symboles préfixés `_`). Modules courts, singuliers, minuscules (`context.py`, `rule.py`, `dsl.py`, `engine.py`, `trace.py`). Verbes pour les actions (`evaluate`, `compile`, `replay`, `commit`), noms pour les objets. Aucune abréviation cryptique dans l'API publique, aucun nom générique creux (`process`, `handle`).

**Q2 — Conventions de nommage du stockage**
Clés hiérarchiques à deux-points, préfixées par l'entité (aligné sur le pattern d'accès dominant : "tout savoir sur l'entité X") :
```
entity:{entity_id}:context:latest
entity:{entity_id}:context:v:{version}
entity:{entity_id}:fact:{fact_id}
entity:{entity_id}:signal:{signal_id}
rule:{rule_id}:compiled
trace:{decision_id}
index:alpha:{field}:{op}:{value}
```
Préfixe global multi-tenant optionnel, configurable sur l'adaptateur `StateBackend`, vide par défaut. Le stockage des `DecisionTrace` doit avoir une politique de rétention dès la première implémentation, même naïve (max-age ou max-count) — sans ça, croissance non bornée garantie.

**Q3 — Hiérarchie d'exceptions**
Arbre à deux branches, miroir exact de la politique Q5 (compilation vs exécution) :
```
EngineError
├── EngineConfigurationError
│   ├── EngineNotCompiledError
│   ├── EngineAlreadyCompiledError
│   ├── DuplicateRuleError
│   ├── InvalidConditionError      (validée à compile(), pas à l'exécution)
│   └── InvalidEffectError
├── EngineRuntimeError
│   ├── RuleEvaluationError        (rule_id, __cause__, signal_id)
│   ├── ContextCorruptionError
│   └── ClockError
└── BackendError                    (adaptateurs de persistance, hors cœur)
```

**Q4 — Tie-breaking de priorité entre règles à égalité**
Ordre d'insertion stable, implémenté via le tri stable garanti par Python (`sorted(rules, key=priority, reverse=True)`). `DecisionTrace.evaluation_order` enregistre l'ordre exact d'évaluation de chaque cycle, pour audit. Garantie documentée : entrées identiques + ordre d'enregistrement identique ⇒ sorties bit-à-bit identiques, indépendamment de l'environnement d'exécution.

**Q5 — Gestion d'erreur pendant l'évaluation**
Fail loud à la compilation (systématique, aucune option). À l'exécution, `EngineConfig.rule_error_policy: Literal["continue", "fail_fast", "fail_loud"] = "continue"` :
- `continue` (défaut) : exception capturée, règle marquée `crashed` dans la trace, les autres règles continuent.
- `fail_fast` : arrête les règles restantes de ce cycle, conserve les effets déjà produits.
- `fail_loud` : l'exception remonte à l'appelant — réservé aux tests/CI.
Une règle qui plante n'applique jamais partiellement son `context_delta` — tout ou rien. `Decision.has_errors: bool` pour vérification rapide sans parcourir la trace complète.

**Réinjection des signaux dérivés** (question soulevée à trois reprises par Kimi sans jamais avoir été tranchée — fermée ici) : file d'attente interne, pas de réinjection immédiate dans le même cycle. `max_derived_depth = 3` par défaut, configurable, pour empêcher toute cascade infinie.

---

## 8. Architecture de dossiers et fichiers (verrouillée)

**Principe d'évolution** (formulation corrigée après le tour multi-IA) : un symbole public peut migrer d'un fichier plat vers un sous-package sans jamais casser un import déjà documenté comme public, à condition stricte que le chemin d'import promis reste résolu vers le même symbole — par réexport dans un `__init__.py`. `__all__` documente et protège la surface publique contre les imports `*` et l'introspection des outils ; ce n'est pas lui qui garantit la stabilité du chemin d'import — c'est la présence continue du symbole dans le namespace du chemin promis.

**Portée du contrat public** : seul `sinmonto.Symbole` (import depuis la racine du package) est garanti stable. Les chemins qualifiés par module (`sinmonto.core.Symbole`) ne sont jamais promis — maintenir deux surfaces de stabilité au lieu d'une double la promesse à tenir sans bénéfice proportionnel. Conséquence directe : tous les fichiers internes sont préfixés `_`, sans exception, pour qu'aucune ambiguïté ne se pose sur ce qui est garanti. Tout import direct d'un fichier préfixé `_` est non supporté et peut changer sans préavis entre versions mineures.

**Structure physique** : v1.0 (et tant que le nombre de fichiers reste faible) reste plate. La séparation `api/`/`_internal/` de la Q1 initiale est reportée jusqu'à ce que le package dépasse 15 fichiers à la racine — jusque-là, la convention `_` + `__all__` suffit et est plus agile.

**v1.0** :
```
sinmonto/
├── __init__.py       # seul chemin d'import public garanti, exports via __all__
├── _version.py
├── _exceptions.py    # racine du graphe de dépendances internes — n'importe
│                      # rien d'autre en interne, pour éviter les imports
│                      # circulaires (presque tout en dépend)
├── _core.py
├── _context.py
├── _engine.py
├── _dsl.py
├── _trace.py
└── _testing.py
```

**Principe sous-jacent, pas une prescription d'ordre exact** : le graphe de dépendances internes doit rester acyclique. L'ordre précis des imports dans `__init__.py` est une responsabilité d'implémentation, pas une clause constitutionnelle.

**v5.0, illustration de l'évolution** : chaque fichier plat devient un sous-package de même nom (`_core/`, `_context/`, `_engine/`...), plus `_temporal/` (v2+), `_state/` (v2+), `_workflow/` (v3+) — additifs, jamais de restructuration de l'existant. À chaque étape, `from sinmonto import Fact` reste valide.

**Angles morts comblés (Kimi)**
- Sérialisation : `dataclasses.asdict()` + `json.dumps()` avec encoder custom (`Decimal`, `UUID`, `bytes`). Jamais `pickle` (non sécurisé, non lisible). Aucune dépendance externe.
- `Fact.payload` : champ privé `_payload: dict`, propriété publique `payload` retournant une vue `Mapping` — empêche la mutation accidentelle sans imposer `__slots__` au payload lui-même.
- `EvaluationResult.derived_signals` (pas `derived_facts`) — un fait dérivé doit être encapsulé dans un `Signal` pour être réinjecté, la séparation Signal/Fact tient jusqu'au bout de la chaîne.

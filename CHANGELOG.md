# Changelog

Toutes les modifications notables de ce projet sont documentées dans ce fichier.
Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/)
(les versions `0.x.y` sont instables par convention — l'API n'est pas encore figée).

L'historique détaillé — comment chaque bug a été trouvé et corrigé, y compris
les fausses pistes — vit dans [`docs/journal-integration.md`](docs/journal-integration.md).
Ce fichier-ci reste volontairement lisible en quelques minutes.

## [Unreleased]

### Changed
- Racine du dépôt allégée : les documents de gouvernance (constitutions, journal
  d'intégration, roadmap, contrat vivant) déplacés vers `docs/`. Aucun changement
  fonctionnel du noyau.

## [0.1.0rc3] - 2026-08-07

### Fixed
- `Fact.payload` / `Effect.payload` : copie **profonde** (`copy.deepcopy`) au lieu
  d'une copie superficielle — une valeur imbriquée (liste, dict) mutée après
  construction ne pouvait plus corrompre l'objet, mais restait encore accessible
  en mutation directe à travers le proxy. `Effect.payload` n'avait auparavant
  aucune protection du tout.
- Packaging : `CLAUDE.md` (symlink vers `AGENTS.md`) correctement préservé lors
  de la création d'archives (`zip -y`).

### Changed
- La garantie de déterminisme bit-à-bit (mêmes entrées ⇒ même sortie) exclut
  désormais explicitement `DecisionTrace.trace_id` (UUID généré à chaque
  évaluation, non reproductible par construction).

## [0.1.0rc2] - 2026-08-07

### Added
- Atomicité réelle des règles : snapshot de `ctx._values` avant chaque
  `rule.evaluate()`, restauré si la règle lève une exception — une mutation
  directe via `ctx.set()` ne survit plus à un crash.
- Validation `Signal.entity_id` contre `fact.entity_id` (`ValueError` explicite
  si les deux sont fournis et diffèrent).
- Validation à la construction des opérateurs `FieldCondition` et des `kind`
  de `CompositeCondition` (`InvalidConditionError` immédiate).
- `InvalidEffectError` sur un retour d'action non reconnu, ou un retour direct
  d'`EvaluationResult` (désormais interdit — pouvait écraser la trace déjà
  calculée par la règle).
- Copie défensive de `Fact._payload` à la construction.
- `causality` chaînée : `(fact.fact_id, *fact.causality)` pour un fait,
  `(signal.signal_id,)` pour un timer (au lieu de vide).
- Code de sortie non nul du mini-runner de tests (`_testing.py`) en cas
  d'échec — exploitable en CI.

### Fixed
- Copie profonde du contexte à `commit()` et au rechargement d'un
  `FrozenContext` existant — un objet imbriqué muté après coup ne corrompt
  plus rétroactivement un état déjà figé.
- `InMemoryFactStore(max_facts=0)` lève un `ValueError` clair au lieu d'un
  `IndexError` obscur.

### Changed
- Contrat public clarifié : les 37 noms de `sinmonto.__all__` sont la
  surface stable, remplaçant un placeholder de documentation ("Symbole")
  jamais réellement implémenté.
- Version, licence (Apache-2.0) et nom du package verrouillés de façon
  cohérente dans tous les fichiers de gouvernance.

## [0.1.0-rc1] - 2026-08-04

### Added
- Première version assemblée et testée de bout en bout du noyau `sinmonto`.
- Objets fondamentaux : `Fact`, `Signal`, `Effect`, `Decision`, `EvaluationResult`,
  horloge injectée (`Clock` / `ManualClock`).
- Contexte à deux phases (`EvaluationContext` mutable → `FrozenContext` immuable
  via `commit()`), avec persistance par entité (`ContextStore` /
  `InMemoryContextStore`).
- DSL de conditions (`Field`, opérateurs, compositions AND/OR/NOT) et
  décorateur `@rule`.
- Moteur (`DecisionEngine`) : indexation alpha légère, `compile()` /
  `evaluate()`, politiques d'erreur `continue` / `fail_fast` / `fail_loud`.
- Traces d'explication en arbre (`ConditionTrace`, `RuleTrace`, `DecisionTrace`).
- Tie-breaking déterministe à priorité égale (ordre d'insertion stable).
- Suite de tests interne sans dépendance externe (mini-runner par module +
  `examples/end_to_end.py`).

### Known limitations (assumées, documentées dès le départ)
- Signaux dérivés acceptés par l'API mais non traités (pas de cascade de règles).
- `RuleTrace.duration_ms` toujours à zéro (non mesuré).
- Pas de fenêtres temporelles, de FSM, ni de `engine.replay()`.

# Changelog

Toutes les modifications notables de ce projet sont documentées dans ce fichier.
Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/)
(les versions `0.x.y` sont instables par convention — l'API n'est pas encore figée).

L'historique détaillé — comment chaque bug a été trouvé et corrigé, y compris
les fausses pistes — vit dans [`docs/journal-integration.md`](docs/journal-integration.md).
Ce fichier-ci reste volontairement lisible en quelques minutes.

## [Unreleased]

## [0.1.0rc6] - 2026-09-23

### Fixed
- Marqueur `py.typed` (PEP 561) manquant alors que `pyproject.toml`
  déclare déjà le classifier `"Typing :: Typed"` — les outils de typage
  (mypy, pyright) ne faisaient pas confiance aux annotations d'un
  `sinmonto` installé sans ce fichier. Ajouté ; build réel vérifié
  (`python -m build` + `twine check`) sur sdist et wheel.
- Deux notes de doc obsolètes nettoyées (`constitution-noyau.md` §12/§13) :
  le benchmark de charge et le packaging listés comme "pas encore faits"
  l'étaient déjà.

### Note
Rien ne bloque encore un `0.1.0` stable côté code : les points de
`constitution-noyau.md` §12 "reste ouvert" sont explicitement hors
scope pour cette preview, pas des manques. Le vrai jalon restant est
externe : publier sur PyPI (workflow prêt, jamais déclenché) pour
obtenir le premier retour d'usage réel que le README pose comme condition
avant de considérer la 0.x figée.

## [0.1.0rc5] - 2026-09-22

### Fixed
- `AlphaIndex` écartait silencieusement une règle `NOT` (ex. `~(Field("vip") == True)`)
  quand le champ concerné est **absent** du fait — précisément le cas où la
  condition doit matcher. Violait le contrat "un sur-ensemble de candidates,
  jamais un sous-ensemble". Toute règle dont l'arbre de condition contient un
  `NOT` va désormais dans `_unindexed` (toujours candidate).
- `InMemoryFactStore.query()` pouvait lever `KeyError` si un `fact_id` était
  ajouté deux fois (redélivrance amont "at-least-once") et que la première
  occurrence était évincée du ring buffer.
- `_EngineJSONEncoder` plantait (`UnicodeDecodeError`) sur des `bytes` qui ne
  sont pas de l'UTF-8 valide — encode maintenant en base64, sans exception
  possible quelle que soit la séquence d'octets.
- `pyproject.toml` restait à `0.1.0rc3` alors que `sinmonto.__version__` disait
  déjà `0.1.0rc4` — deux sources de vérité contradictoires (`pip show sinmonto`
  mentait). Passé en versioning dynamique (`[tool.hatch.version]` lit
  `sinmonto/_version.py`) : une seule source de vérité désormais, structurellement.
- File FIFO de la cascade de signaux dérivés : `list.pop(0)` (O(n), donc O(n²)
  cumulé) remplacé par `collections.deque.popleft()` (O(1)).

Les 4 bugs et le point de performance ont été trouvés par un audit adversarial
(Grok, campagne de benchmark rc4) — détail complet, reproduction et correction
de chacun : [`journal-integration.md`](docs/journal-integration.md), entrée
du 22 septembre 2026.

### Added
- `docs/benchmark-rc4.md` et `scripts/benchmark.py` — chiffres mesurés
  (pas estimés) et harness reproductible pour l'évaluation, la cascade, le
  `FactStore`, la comparaison avec une boucle Python nue et la mémoire.

## [0.1.0rc4] - 2026-09-22

### Added
- Cascade de signaux dérivés : `EvaluationResult.derived_signals` est
  désormais traité par une file FIFO interne à `evaluate()` (jamais
  réinjecté dans le même cycle), avec `max_derived_depth` réellement
  appliqué (défaut : 3). Une seule `Decision` agrège les effets et la
  trace de toute la cascade.
- `MaxDerivedDepthExceededError` (`EngineRuntimeError`) : levée quand
  `rule_error_policy="fail_loud"` et qu'un signal dérivé dépasserait
  `max_derived_depth` ; sous `continue`/`fail_fast`, le signal est
  abandonné mais tracé explicitement (`rule_id="__max_derived_depth__"`)
  et `Decision.has_errors` passe à `True` — jamais de troncature
  silencieuse.
- `RuleTrace.hop` et `RuleTrace.trigger_signal_id` (défauts
  rétrocompatibles) pour distinguer deux évaluations du même `rule_id` à
  des hops différents de la cascade.
- 8 nouveaux tests couvrant la cascade (agrégation en une Decision,
  visibilité du contexte entre hops, chaînage de la causality — y compris
  à travers deux `entity_id` différents —, comportement aux deux bornes
  de `max_derived_depth`).

### Changed
- Racine du dépôt allégée : les documents de gouvernance (constitutions, journal
  d'intégration, roadmap, contrat vivant) déplacés vers `docs/`. Aucun changement
  fonctionnel du noyau.
- Surface publique : 38 noms dans `sinmonto.__all__` (37 + `MaxDerivedDepthExceededError`).

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

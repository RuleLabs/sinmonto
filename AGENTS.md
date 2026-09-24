# AGENTS.md

Instructions pour toute IA (Claude Code, Cursor, Copilot, ou autre) travaillant sur ce dépôt. Lis ceci avant de toucher au code.

**`CLAUDE.md` est un lien symbolique vers ce fichier** (`CLAUDE.md -> AGENTS.md`), pas une copie — un seul contenu, deux points d'entrée. **Ne jamais éditer via `sed -i`, `> CLAUDE.md` ou tout outil qui réécrit en remplaçant le fichier à ce chemin** : ces outils font typiquement écriture-dans-un-temp-puis-rename, ce qui remplace le lien lui-même par un fichier indépendant — le symlink casse silencieusement, `CLAUDE.md` et `AGENTS.md` divergent sans erreur visible. Éditer `AGENTS.md` directement, ou un outil d'édition qui ouvre le chemin en écriture plutôt que de le remplacer (`str_replace`, la plupart des éditeurs). Trouvé deux fois en pratique : `zip -qr` sans `-y` remplaçait le lien par une copie du fichier cible à l'empaquetage (2026-08) ; `sed -i` sur le chemin `CLAUDE.md` le remplaçait par un fichier indépendant à l'édition (2026-09) — voir `journal-integration.md` pour le détail des deux.

**Ce fichier est pour modifier `sinmonto` lui-même.** Si tu dois juste *utiliser* la bibliothèque dans un autre projet (écrire des règles, appeler `evaluate()`...), lis [`UTILISATION.md`](./UTILISATION.md) à la place — plus court, orienté API, pas gouvernance du dépôt.

## Ce projet en une phrase

`sinmonto` — moteur de décision événementiel, explicable, en Python pur, zéro dépendance. Voir `docs/fr/README.md` pour l'usage (le `README.md` à la racine est en anglais depuis la traduction FR/EN), `docs/constitution-finale.md` et `docs/constitution-noyau.md` pour l'architecture complète.

## Règles non négociables

Ne propose jamais d'architecture alternative aux 10 décisions ci-dessous. Ne les redébats pas. Si une impossibilité technique apparaît en implémentant réellement (pas en théorie), signale-la explicitement — ne la contourne pas en silence, ne modifie pas la spec toi-même pour l'éviter.

1. Pas de réseau Rete complet — indexation alpha légère uniquement (par nom de champ).
2. `Context` mutable pendant un cycle, figé en `FrozenContext` immuable à la fin (`commit()`) — jamais d'immuabilité totale à la façon persistante.
3. `Signal` (déclencheur, porte `entity_id`) et `Fact` (information) sont deux types distincts.
4. Effects-as-data : aucune règle n'exécute d'effet de bord. Elle retourne des `Effect` décrits ; un exécuteur séparé les applique.
5. Explicabilité native : chaque condition, vraie ou fausse, doit être traçable via l'arbre `ConditionTrace`.
6. Pas de durabilité multi-jours dans le cœur. `ContextStore`/`FactStore` abstraits, implémentations en mémoire par défaut.
7. Temps injecté (`Clock`), jamais `time.time()` dans le moteur.
8. `engine.compile()` verrouille la configuration ; aucune règle ajoutée après sans lever `EngineAlreadyCompiledError`.
9. `__slots__` sur les objets internes chauds — jamais sur le `payload` utilisateur (reste un `dict` libre, exposé en lecture seule via `MappingProxyType`).
10. Protocole `Evaluable` commun, classes distinctes (`Rule`, futures `Transition`) qui l'implémentent — pas de type générique fourre-tout.

## Conventions de nommage et de fichiers

- Tous les fichiers internes sont préfixés `_` (`_core.py`, `_engine.py`...), sans exception. Seul `__init__.py` est un chemin d'import public garanti — voir `docs/constitution-finale.md` §8.
- Les 37 noms de `sinmonto.__all__` sont le contrat public stable (`from sinmonto import <nom>`). Ne jamais documenter ni recommander un import qualifié par module (`sinmonto._core.Fact`). (Avant 2026-08, cette ligne disait « seul `sinmonto.Symbole` » — un placeholder jamais rempli, corrigé en revue croisée.)
- PEP8 strict. Verbes pour les actions (`evaluate`, `compile`, `commit`), noms pour les objets.

## Tests

Les tests vivent dans `tests/`, séparés du code source (Phase 3 de la restructuration, 2026-08) — pas dans les modules `sinmonto/*.py`. Zéro dépendance de test (`tests/run_all.py`, runner interne à découverte automatique, pas livré dans le package installé).

```bash
python3 tests/run_all.py              # tout, depuis la racine du dépôt
python3 tests/run_all.py test_core    # un seul module, pour déboguer
```

Les imports internes sont relatifs (`from ._core import Fact`) — un module ne peut donc pas s'exécuter avec `python3 sinmonto/_core.py` en direct. `pip install -e .` (voir `docs/fr/CONTRIBUTING.md`) rend `sinmonto` importable depuis `tests/` ; `run_all.py` ajoute aussi la racine du dépôt à `sys.path` en secours.

## État actuel (v0.1.0rc6 — preview technique)

Fait et testé de bout en bout (53 tests, `tests/` + intégration) : objets fondamentaux, contexte à deux phases avec persistance (`ContextStore`), trace d'explication en arbre, DSL avec opérateurs, moteur avec indexation alpha, tie-breaking déterministe, gestion d'erreur (`continue`/`fail_fast`/`fail_loud`), cascade de signaux dérivés (file FIFO `deque`, `max_derived_depth`, causality chaînée par hop).

Corrigé en revue croisée multi-IA (2026-08) — voir `docs/journal-integration.md` : atomicité réelle des règles (snapshot/restore de `ctx`, y compris mutation directe), copie profonde du contexte (y compris `Fact`/`Effect.payload`), validation `Signal.entity_id`/opérateurs de condition/kind composite/retours d'action, `causality` chaînée, code de sortie non nul du runner de tests sur échec.

Cascade de signaux dérivés câblée (2026-09), synthèse de revue croisée 5 IA — voir `docs/journal-integration.md`.

Corrigé en audit adversarial (2026-09, Grok, benchmark rc4) : `AlphaIndex` qui écartait silencieusement un `NOT` sur champ absent, `KeyError` sur `fact_id` dupliqué dans `InMemoryFactStore`, `_EngineJSONEncoder` qui plantait sur `bytes` non-UTF-8, `pyproject.toml` désynchronisé de `_version.py` (passé en versioning dynamique), `list.pop(0)` → `deque.popleft()` dans la cascade. Voir `docs/journal-integration.md` et `docs/benchmark-rc4.md`.

Pas encore fait, ne pas assumer que c'est câblé : mesure réelle de `duration_ms`, aplatissement des AND chaînés dans la trace, politique de rétention sur les stores mémoire. Voir `docs/roadmap-vision.md` et `docs/journal-integration.md` pour le détail et l'historique complet des décisions.

## Processus

Toute évolution architecturale (pas une simple implémentation) passe par `docs/contrat-vivant-gabarit.md` — mission écrite, rapport structuré en retour, synthèse avant verrouillage. Ne pas modifier `docs/constitution-finale.md` unilatéralement.

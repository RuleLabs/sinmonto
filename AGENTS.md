# AGENTS.md

Instructions pour toute IA (Claude Code, Cursor, Copilot, ou autre) travaillant sur ce dépôt. Lis ceci avant de toucher au code.

## Ce projet en une phrase

`sinmonto` — moteur de décision événementiel, explicable, en Python pur, zéro dépendance. Voir `README.md` pour l'usage, `docs/constitution-finale.md` et `docs/constitution-noyau.md` pour l'architecture complète.

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

Chaque module a son propre bloc `if __name__ == "__main__":` en bas de fichier, zéro dépendance de test (`_testing.py`, mini-runner interne). Pour tester un module isolément :

```bash
python3 -m sinmonto._core      # depuis le dossier PARENT de sinmonto/
```

Les imports internes sont relatifs (`from ._core import Fact`) — un module ne peut donc pas s'exécuter avec `python3 _core.py` en direct, seulement via `-m`.

## État actuel (v0.1.0rc2 — preview technique)

Fait et testé de bout en bout (41 tests, modules + intégration) : objets fondamentaux, contexte à deux phases avec persistance (`ContextStore`), trace d'explication en arbre, DSL avec opérateurs, moteur avec indexation alpha, tie-breaking déterministe, gestion d'erreur (`continue`/`fail_fast`/`fail_loud`).

Corrigé en revue croisée multi-IA (2026-08) — voir `docs/journal-integration.md` : atomicité réelle des règles (snapshot/restore de `ctx`, y compris mutation directe), copie profonde du contexte, validation `Signal.entity_id`/opérateurs de condition/kind composite/retours d'action, copie défensive de `Fact._payload`, `causality` chaînée, code de sortie non nul du mini-runner sur échec.

Pas encore fait, ne pas assumer que c'est câblé : file d'attente des signaux dérivés (`max_derived_depth`), mesure réelle de `duration_ms`, aplatissement des AND chaînés dans la trace. Voir `docs/roadmap-vision.md` et `docs/journal-integration.md` pour le détail et l'historique complet des décisions.

## Processus

Toute évolution architecturale (pas une simple implémentation) passe par `docs/contrat-vivant-gabarit.md` — mission écrite, rapport structuré en retour, synthèse avant verrouillage. Ne pas modifier `docs/constitution-finale.md` unilatéralement.

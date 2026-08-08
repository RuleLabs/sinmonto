# Contribuer à sinmonto

Merci de t'intéresser à `sinmonto` (*Sɛ́n mɔto*, fon pour « moteur de règle »).

Ce projet a été développé en solo depuis un téléphone (Termux, Android — pas
de PC), avec une gouvernance multi-IA inhabituelle : les décisions
architecturales passent par des revues croisées documentées, pas par une
seule opinion. Une contribution externe est bienvenue, dans ce cadre.

## Avant de commencer

1. Lis [`README.md`](README.md) — usage et limitations connues.
2. Lis [`docs/constitution-finale.md`](docs/constitution-finale.md) §2 — les
   **10 décisions architecturales verrouillées**. Elles ne se redébattent pas
   dans une issue ou une PR. Si une impossibilité technique réelle apparaît
   en implémentant (pas en théorie), signale-la explicitement — ne la
   contourne pas en silence.
3. Si tu touches au noyau : [`AGENTS.md`](AGENTS.md) pour les conventions de
   code et la routine de vérification exacte.

## Les 10 décisions verrouillées

1. Pas de réseau Rete complet — indexation alpha légère uniquement.
2. `Context` mutable pendant un cycle d'évaluation, figé en `FrozenContext`
   immuable à la fin (`commit()`).
3. `Signal` (déclencheur) et `Fact` (information) sont deux types distincts.
4. Effects-as-data : aucune règle n'exécute d'effet de bord — elle retourne
   des `Effect` décrits, un exécuteur séparé les applique.
5. Explicabilité native — chaque condition, vraie ou fausse, doit être
   traçable.
6. Pas de durabilité multi-jours dans le cœur (`ContextStore`/`FactStore`
   abstraits, implémentations mémoire par défaut).
7. Temps injecté (`Clock`), jamais `time.time()` dans le moteur.
8. `engine.compile()` verrouille la configuration.
9. `__slots__` sur les objets internes chauds — jamais sur le `payload`
   utilisateur.
10. Protocole `Evaluable` commun, classes distinctes qui l'implémentent.

## Le filtre v1.0

Avant de proposer une fonctionnalité : *« est-ce que ça rapproche réellement
la v1.0, ou est-ce qu'on rêve d'une fonctionnalité qui n'a peut-être jamais
besoin d'exister maintenant ? »* Si c'est la seconde réponse, l'idée a sa
place dans [`docs/roadmap-vision.md`](docs/roadmap-vision.md), pas dans le
noyau tout de suite.

## Installer et lancer les tests

```bash
git clone https://github.com/RuleLabs/sinmonto.git
cd sinmonto
pip install -e .
```

Zéro dépendance de runtime ni de test — pas de `pytest`. Chaque module a son
propre bloc `if __name__ == "__main__":` qui fait tourner le mini-runner
interne (`_testing.py`). Depuis la racine du dépôt :

```bash
python3 -m sinmonto._exceptions
python3 -m sinmonto._core
python3 -m sinmonto._trace
python3 -m sinmonto._testing
python3 -m sinmonto._context
python3 -m sinmonto._dsl
python3 -m sinmonto._engine
python3 examples/end_to_end.py
```

*(`./scripts/test_all.sh` fait tourner cette liste en une commande.)*

Les imports internes sont relatifs : un module ne s'exécute pas avec
`python3 sinmonto/_core.py` en direct, uniquement via `python3 -m sinmonto._core`
depuis le dossier **parent** de `sinmonto/`. Un échec sort avec un code non
nul (`os._exit(1)`), exploitable en CI.

## Comment proposer un changement

**Typo, lien cassé, correction de doc** — PR directe, pas besoin d'issue.

**Correction de bug** — Ouvre une issue courte (comportement attendu vs
observé, comment reproduire, sortie du mini-runner si pertinent). Une PR
peut suivre immédiatement si tu as déjà le correctif.

**Évolution architecturale** (nouvelle fonctionnalité, changement de
comportement, nouvelle primitive) — Ouvre une issue d'abord. Ne commence pas
le code avant que la direction soit validée. Ces décisions passent par le
processus du **contrat vivant** ([`docs/contrat-vivant-gabarit.md`](docs/contrat-vivant-gabarit.md)) :
mission écrite, revues croisées, rapport structuré, synthèse avant
verrouillage. Tu peux y participer — proposer une mission, répondre à un
rapport — mais la décision finale revient au mainteneur.

### Ce qu'on attend dans une PR
- Un changement net, un périmètre clair — pas de refonte cachée dans un
  patch de trois lignes.
- Les tests concernés lancés localement, et `examples/end_to_end.py`.
- La doc mise à jour (`README.md`, `CHANGELOG.md`, ou `docs/`) si le
  comportement visible change.
- Aucun import direct depuis un module interne (`from sinmonto._core import
  Fact`) — seule la surface `sinmonto.__all__` (37 noms) est garantie.

## Le ton attendu

[`docs/journal-integration.md`](docs/journal-integration.md) documente
honnêtement les bugs, les fausses pistes et les erreurs de revue — la
tienne y compris, le cas échéant. Ce n'est pas une gêne à cacher, c'est une
valeur du projet. *« J'ai d'abord essayé X, ça ne marchait pas parce que Y,
j'ai finalement opté pour Z »* est un format de description de PR
parfaitement valide ici — préférable à un historique lissé.

## Revue

Le dépôt est géré en solo, en preview 0.x. Le délai de réponse peut varier
selon la disponibilité du mainteneur (depuis son téléphone). Pas d'exigence
de SLA ; un ping poli après deux semaines sans nouvelles est bienvenu.

## Licence

En contribuant, tu acceptes que ta contribution soit publiée sous la licence
du projet : [Apache License 2.0](LICENSE).

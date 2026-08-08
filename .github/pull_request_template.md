## Résumé
Décris en quelques lignes ce que fait cette PR. `Closes #...` si applicable.

## Type de changement
- [ ] Correction de bug
- [ ] Documentation uniquement
- [ ] Comportement / API (décrire l'impact ci-dessous)
- [ ] Scaffolding / outillage

## Checklist
- [ ] J'ai lu `docs/constitution-finale.md` §2 et cette PR ne contredit
      aucune des 10 décisions verrouillées.
- [ ] Tests concernés lancés localement (`python3 -m sinmonto._...`, voir
      `CONTRIBUTING.md`), tous verts.
- [ ] `python3 examples/end_to_end.py` passe.
- [ ] Aucun import direct hors `from sinmonto import ...` (surface
      `sinmonto.__all__` uniquement).
- [ ] Doc mise à jour si le comportement observable change (`README.md`,
      `CHANGELOG.md`, ou `docs/`).

## Impact sur la surface publique
- [ ] Aucun changement de contrat public
- [ ] Changement de contrat public — expliqué ci-dessous

## Notes pour la revue

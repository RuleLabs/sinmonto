# Benchmark rc4

Chiffres mesurés, pas estimés — reproductibles avec `python3 scripts/benchmark.py`
depuis la racine du dépôt. Harness écrit par Grok (audit adversarial + benchmark
rc4, 2026-09) ; les chiffres ci-dessous viennent d'une exécution de ce script
**après** les 4 bugs et le fix de performance trouvés par cette même revue (voir
`journal-integration.md`, entrée du 22 septembre 2026) — pas de la première
passe, pré-correctifs.

**Environnement de cette exécution** : Python 3.12.3 (CPython), 1 vCPU,
`sinmonto` 0.1.0rc4. Une exécution sur un autre CPU donnera d'autres chiffres
absolus — c'est la *forme* des courbes qui est portable, pas les microsecondes.

## 1. Évaluation — le rôle de l'index

| Règles | 1 seule candidate (indexé) | Toutes candidates (pire cas) |
|---:|---:|---:|
| 1 | 15,7 µs | 15,5 µs |
| 10 | 15,7 µs | 57,9 µs |
| 100 | 17,2 µs | 501 µs |
| 1 000 | 46,9 µs | 4 924 µs |

`AlphaIndex` fait exactement ce qu'il promet : le coût réel dépend du nombre de
règles **candidates** pour un fait donné, pas du nombre total de règles
compilées. Le coût qui reste même à 1 candidate (~47 µs à 1000 règles, contre
~16 µs à 1 règle) vient du scan de `_rule_order` pour reconstruire l'ordre
déterministe à chaque hop — connu, pas un bug, différé en optimisation
(§12 de `constitution-noyau.md`).

## 2. Cascade de signaux dérivés

Linéaire, coût marginal ~15-17 µs par hop :

| Profondeur | Hops exécutés | Médiane |
|---:|---:|---:|
| 0 | 1 | 14,2 µs |
| 3 | 4 | 65,5 µs |
| 10 | 11 | 175,9 µs |

Le branchement (plusieurs signaux dérivés par hop), en revanche, explose
combinatoirement — attendu, c'est la taille du graphe métier qui domine, pas
le moteur :

| Profondeur × branchement | Évaluations | Médiane |
|---:|---:|---:|
| 3 × 2 | 15 | 235 µs |
| 6 × 2 | 127 | 2 068 µs |
| 4 × 3 | 121 | 1 937 µs |

## 3. FactStore — scan linéaire, pas d'index par entité (assumé)

| Faits stockés | `query()` sur 1 entité |
|---:|---:|
| 1 000 | 85 µs |
| 10 000 | 889 µs |
| 100 000 | 9 031 µs |

Confirme la doc existante : `InMemoryFactStore` est prévu pour tests/démo/prototype,
pas comme base analytique de production (`constitution-noyau.md` §12, point non
bloquant).

## 4. Comparaison avec une boucle Python nue

L'overhead face à une boucle sans trace, sans `Fact`, sans `Decision`, sans
persistance, sans validation : ×105 à 1 règle, ×362 à 1000 règles. **Ne pas lire
ça comme "sinmonto est 362× plus lent qu'un concurrent"** — la baseline ne fait
presque rien, elle mesure le prix de l'architecture (atomicité, traçabilité,
déterminisme), pas la valeur relative d'un produit face à un autre moteur de
règles réel.

## 5. Le vrai coût : l'atomicité, pas la cascade ni l'index

Le proxy le plus direct : `fail_loud` (5,7 µs, arrêt immédiat à la première
exception) contre `continue`/`fail_fast` (~16,6 µs, isolation par snapshot).
La différence est le prix du `deepcopy` de `ctx._values` pris avant **chaque**
règle candidate pour garantir qu'une règle qui plante n'applique jamais
partiellement son `context_delta` (décision verrouillée, `constitution-finale.md`
Q5). C'est un compromis délibéré, pas une perte de perf accidentelle — mais
c'est le premier mur si des utilisateurs stockent de gros contextes (plusieurs
centaines de clés).

## 6. Mémoire

+658 Ko après 1 000 évaluations (50 règles, entités distinctes) — dominé par
la rétention des `Fact` et des derniers `FrozenContext` par entité. Croissance
attendue, pas une fuite ; confirme que l'absence de politique de rétention
reste le vrai sujet pour un usage longue durée (déjà noté, non bloquant).

## Ce que cette campagne a trouvé (au-delà des chiffres)

L'audit adversarial qui accompagnait ce benchmark a trouvé 4 bugs réels
(3 dans le moteur, corrigés avant ces mesures — un `NOT` sur champ absent
silencieusement jamais évalué par `AlphaIndex`, un `fact_id` dupliqué qui
pouvait faire planter `FactStore.query()`, un encodeur JSON qui plantait sur
des `bytes` non-UTF-8 — et 1 dans le packaging, `pyproject.toml` resté à
`0.1.0rc3`). Détail complet, avec comment chacun a été reproduit et corrigé :
`journal-integration.md`, entrée du 22 septembre 2026.

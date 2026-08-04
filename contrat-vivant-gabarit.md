# Contrat vivant — gabarit réutilisable

**Comment s'en servir** : à chaque tour, tu copies ce gabarit, tu remplis la PARTIE VARIABLE (état des modules + mission précise), tu laisses la PARTIE IMMUABLE telle quelle, et tu envoies le tout à l'IA concernée. Elle répond avec le gabarit de rapport en bas de ce fichier. Ce document remplace l'historique de conversation — l'IA n'a besoin de rien d'autre pour être à jour.

---

## PARTIE IMMUABLE (copier tel quel à chaque tour, ne pas modifier)

### 1. Contexte du projet
Moteur de décision événementiel en Python pur, zéro dépendance externe, développé seul depuis un téléphone (Termux/Pydroid/ACode, pas de PC). Cas d'usage cible : fintech/fraude en priorité, généralisable à IoT, e-commerce, cybersécurité, BPM.

### 2. Décisions verrouillées — non-débattables
*(copié depuis `constitution-finale.md` §2, la source canonique — si ce document change, cette copie doit être mise à jour)*
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

### 3. Règle d'or pour toute IA qui reçoit ce document
- Ne pas proposer d'architecture alternative aux 10 points ci-dessus.
- Ne pas redébattre une décision déjà verrouillée.
- Si une impossibilité technique apparaît en implémentant réellement (pas en théorie), la signaler explicitement dans le rapport — ne pas la contourner en silence, ne pas modifier la spec soi-même pour l'éviter.
- **Le filtre v1.0, à appliquer à chaque suggestion, y compris les tiennes** : *"est-ce que ça rapproche réellement la v1.0, ou est-ce qu'on rêve d'une fonctionnalité qui n'a peut-être jamais besoin d'exister maintenant ?"* Si la réponse est la seconde, ne pas l'implémenter — la signaler dans la section "Idée notée pour la roadmap" du rapport, et rien de plus.

---

## PARTIE VARIABLE (à remplir avant chaque envoi)

### 4. État actuel des modules

| Module | Statut | Interface figée ? |
|---|---|---|
| core.py | ... | oui/non |
| context.py | ... | oui/non |
| engine.py | ... | oui/non |
| dsl.py | ... | oui/non |
| trace.py | ... | oui/non |

*Pour chaque module marqué "interface figée : oui", coller ici les signatures exactes (classes, méthodes, types) — le contrat que les autres modules peuvent supposer stable. Pas besoin de coller l'implémentation complète, seulement l'interface.*

### 5. Ta mission pour ce tour

**Destinataire** : [nom de l'IA]
**Type de tour** : [Implémentation / Vérification croisée / Correction ciblée / Contribution constitutionnelle]

[Description précise et bornée de la tâche. Exemples :
- Implémentation : "Écris context.py complet contre l'interface figée de core.py collée ci-dessus."
- Vérification croisée : "Voici les 5 modules déjà écrits (collés ci-dessous). Ton module s'intègre-t-il toujours correctement ? Ne signale que les incompatibilités d'interface, pas des préférences de style."
- Correction ciblée : "Le test suivant échoue avec cette erreur exacte : [...]. Corrige uniquement ce point."
- Contribution constitutionnelle : "Voici 5 questions ouvertes de la Constitution finale, avec une proposition initiale pour chacune. Donne ta position sur chaque point — d'accord, en désaccord (pourquoi), ou amendement — sans rouvrir les 10 décisions déjà verrouillées."]

### 6. Critère d'acceptation
[Comment on saura que c'est bon — ex : "le bloc de test en bas du fichier passe sans erreur", "aucune incompatibilité bloquante signalée"]

---

## Gabarit de rapport attendu en retour

```
# Rapport — [nom IA] — Tour [N] — [module ou tâche]

## Statut : complet / bloqué / partiel

## Écart(s) par rapport au contrat
- (ou "aucun")

## Code produit
[bloc de code]

## Incompatibilités détectées avec d'autres modules (si vérification croisée)
| Module concerné | Problème | Sévérité (bloquant/mineur) |
|---|---|---|

## Tests exécutés et résultat
- ...

## Idée notée pour la roadmap, non implémentée (optionnel)
- (une idée hors-scope v1.0 repérée en cours de route, à mettre dans roadmap-vision.md, pas dans le code)

## Question ouverte pour le prochain tour (optionnel)
- ...
```

---

## Exemple rempli (à titre d'illustration, pas à réutiliser tel quel)

**Mission pour ChatGPT, tour 3** — Type : Implémentation
« Écris `context.py` complet (`EvaluationContext`, `FrozenContext`, `FactStore`) contre l'interface figée de `core.py` ci-dessous : [signatures collées]. Un bloc de test exécutable en bas du fichier. »

**Critère d'acceptation** : le bloc de test s'exécute sans erreur et produit un `FrozenContext` dont `causality` contient bien l'ID du `Fact` d'entrée.

# Journal d'intégration

Un seul fichier, entrées chronologiques, la plus récente en dernier. Sert à
trois choses : garder une trace de ce qui a réellement été tenté (pas
seulement ce qui était prévu), fermer la boucle avec les IA qui ont contribué
à chaque pièce, et éviter de redécouvrir deux fois le même problème.

**Différence avec `roadmap-vision.md`** : la roadmap dit ce qui reste à
faire. Ce journal dit ce qui a été fait, comment ça s'est passé, et ce que ça
a coûté à découvrir.

---

## Format d'une entrée

```markdown
## [Date] — Titre court

**Contexte** : qu'est-ce qu'on essayait de faire, en une phrase.

**Résultat** : succès / partiel / échec, en une phrase.

**Problèmes rencontrés**
1. [Problème] → comment on l'a trouvé → comment on l'a corrigé
2. ...

**Ce qui reste ouvert**
- ...

**Fichiers concernés** : liste
```

Règle : un problème sans "comment on l'a trouvé" n'a pas sa place ici — c'est
justement la partie qui vaut la peine d'être gardée. N'importe qui peut lire
le code final ; ce qui se perd si on ne l'écrit pas, c'est le chemin pour y
arriver.

---

## 31 juillet 2026 — Première intégration réelle : context, dsl, engine

**Contexte** : Kimi, Gemini et DeepSeek pro ont chacun livré une implémentation
complète et testée de leur mission (`_context.py`, `_dsl.py`, `_engine.py`
respectivement, missions issues du contrat vivant). Objectif : les assembler
et vérifier qu'un cycle de décision complet tourne réellement.

**Résultat** : succès — un scénario de bout en bout (deux règles via `@rule`,
une transaction, une décision expliquée par sa trace) tourne sans erreur
après correction de quatre problèmes d'intégration.

**Problèmes rencontrés**

1. **`EvaluationResult.condition_results` était un champ mort.** → Trouvé en
   lisant les trois livraisons côte à côte : Gemini laissait ce champ vide
   (`{}`), DeepSeek pro construisait une trace plate synthétique dans le
   moteur pour compenser — les deux contournaient le même trou sans se voir.
   C'était un oubli de ma part : ce champ datait d'avant l'introduction de
   `ConditionTrace` en arbre, jamais mis à jour. → Corrigé dans `_core.py` :
   le champ s'appelle maintenant `condition_trace` et porte le vrai arbre
   produit par `FieldCondition`/`CompositeCondition.evaluate()`.

2. **Deux classes `Rule` incompatibles.** → Trouvé en lisant `_engine.py` :
   DeepSeek pro avait défini son propre `Rule` (condition = fonction brute)
   en parallèle de celui de `_dsl.py` (condition = objet DSL). Le moteur
   n'aurait jamais réellement utilisé le DSL de Gemini. → Le `Rule` de
   `_engine.py` supprimé, le moteur importe celui de `_dsl.py`. `add_rule()`
   simplifié à un seul paramètre (la condition est déjà `rule.condition`).

3. **`ctx.commit(version=0, causality=...)` ne correspond pas à la
   signature réelle.** → Trouvé à l'exécution (`TypeError` immédiat) : Kimi
   avait implémenté `commit(causality, clock)`, version auto-calculée,
   `clock` obligatoire. DeepSeek pro ne pouvait pas le savoir — sa mission
   ne lui donnait que le stub, pas l'implémentation finale de Kimi, puisque
   les deux tours ont été envoyés en parallèle. → Corrigé l'appel dans
   `_engine.py`.

4. **Un bug dans mon propre test, pas dans le code livré.** → En intégrant
   le test de Gemini, j'ai supposé que `(A & B) & C` donnait un nœud AND à 3
   enfants à plat. Faux : `__and__` empile sans aplatir, ça donne un arbre à
   2 niveaux. Trouvé en faisant tourner le test (`Expected: 3, Actual: 2`).
   → Assertion corrigée pour refléter la vraie forme de l'arbre. La logique
   de court-circuit elle-même était correcte du premier coup.

**Ce qui reste ouvert**
- Persistance du contexte entre deux appels (`ContextStore` proposé,
  constitution-noyau.md §12).
- File d'attente des signaux dérivés (`max_derived_depth`).
- `duration_ms` non mesuré.
- AND chaînés non aplatis dans la trace (cosmétique).

**Fichiers concernés** : `_core.py`, `_context.py`, `_dsl.py`, `_engine.py`,
`__init__.py`

---

## 31 juillet 2026 (suite) — Vérification indépendante par Kimi et Gemini

**Contexte** : les fichiers intégrés envoyés à Kimi et Gemini pour qu'elles
fassent tourner l'ensemble de leur côté et cherchent ce qui reste cassé.

**Résultat** : succès — un vrai bug trouvé par Kimi et corrigé, un vrai bug
trouvé en vérifiant le test de Gemini (pas signalé par le test lui-même) et
corrigé.

**Problèmes rencontrés**

1. **`FrozenContext.values` restait un `dict` mutable si construit
   directement, hors `commit()`.** → Trouvé par Kimi en testant des chemins
   de construction que je n'avais pas essayés (désérialisation, construction
   manuelle). La protection par `MappingProxyType` n'existait que dans
   `commit()`, pas comme invariant de la classe elle-même. → Corrigé par
   Kimi : `__post_init__` sur `FrozenContext` qui convertit systématiquement
   tout `dict` reçu, quel que soit le chemin de construction. Vérifié en le
   faisant tourner ici, tous les tests existants passent toujours.

2. **Un `dict` imbriqué dans une liste retournée par `action()` était
   silencieusement perdu.** → Le test `test_end_to_end.py` de Gemini fait
   `return [Effect(...), {"risk_score": 0.85}]` mais n'affirme jamais que
   `risk_score` arrive dans `context_delta` — le test passait quand même,
   le bug était invisible dans ses propres assertions. Trouvé en écrivant un
   test isolé pour vérifier ce cas précis avant de faire confiance au
   silence du test. → `Rule.evaluate()` dans `_dsl.py` ne traitait un
   élément de liste que s'il était `Effect` ou `Signal`, jamais `dict`.
   Corrigé, avec un test de non-régression qui aurait attrapé ce cas.

**Ce qui reste ouvert** : inchangé depuis l'entrée précédente (persistance
du contexte, file de signaux dérivés, `duration_ms`, AND non aplatis).

**Fichiers concernés** : `_context.py` (Kimi), `_dsl.py`

---

## 1er août 2026 — Revue critique multi-IA : deux bugs réels, un mensonge de doc, et un bug trouvé en testant mon propre test

**Contexte** : quatre revues indépendantes (Kimi, DeepSeek, Gemini, ChatGPT)
sur le code intégré, plus un correctif complet proposé pour les deux bugs
déjà connus. Gemini a fait une "exécution simulée" et n'a rien trouvé de
nouveau — Kimi, DeepSeek et ChatGPT ont réellement fait tourner le code et
ont chacun trouvé quelque chose de réel. Leçon retenue : une revue qui
prétend avoir exécuté le code sans l'avoir vraiment fait se voit à ce
qu'elle rate.

**Résultat** : succès — six corrections appliquées, toutes vérifiées par
exécution réelle, y compris un scénario de persistance sur 3 signaux
consécutifs pour la même entité (compteur qui monte à 3, pas de retour à
zéro).

**Problèmes rencontrés**

1. **Contexte perdu entre évaluations** (déjà su, enfin corrigé). →
   `ContextStore`/`InMemoryContextStore` ajoutés dans `_context.py`, câblés
   dans `DecisionEngine.evaluate()` : chargement du dernier `FrozenContext`
   connu avant de construire l'`EvaluationContext`, sauvegarde après
   `commit()`.

2. **Tie-breaking non déterministe.** → Trouvé par Kimi/DeepSeek en
   remarquant que `AlphaIndex.match()` retourne un `set[str]`, dont l'ordre
   d'itération dépend du hash randomization de Python — vérifié
   concrètement ici en lançant le même `set` dans 3 process séparés, l'ordre
   change bien. Le tri stable par priorité ne pouvait donc pas garantir le
   tie-break par ordre d'insertion promis en Q4. → La liste de candidats est
   reconstruite en filtrant `self._rule_order` (déjà ordonné) plutôt qu'en
   itérant le `set` directement. Testé sur 20 exécutions répétées pour ne
   pas se fier à un seul tirage de hash favorable.

3. **`entity_id` arbitraire ("global") pour les signaux sans fait
   (timers).** → `Signal` porte maintenant `entity_id` explicitement,
   dérivé automatiquement de `fact.entity_id` s'il est absent et qu'un fait
   est présent, obligatoire sinon (`__post_init__` lève `ValueError` sans
   quoi).

4. **`EvaluationResult` sans `__slots__`** — seul objet chaud à y échapper.
   → `slots=True` ajouté.

5. **`FrozenContext` prétendait être "hashable" dans sa docstring, mais ne
   l'était pas** (`hash()` lève `TypeError: unhashable type: 'dict'`). →
   Vérifié : cette promesse n'a jamais été verrouillée dans
   `constitution-noyau.md` — un reliquat d'une proposition très ancienne de
   Kimi, jamais retenue. Corrigé en la rendant explicitement non hashable
   (`__hash__ = None`), avec l'échec immédiat et clair plutôt qu'une
   `TypeError` confuse levée en interne.

6. **`add_rule()` laissait fuir une `AttributeError` brute** sur une
   condition mal formée (`condition="oops"`) au lieu de `InvalidConditionError`.
   → Trouvé par ChatGPT, qui a testé explicitement ce cas. Validation ajoutée
   dans `add_rule()`.

7. **Un bug dans mon propre test de non-régression, pas dans le code livré.**
   → En écrivant le test de persistance (`ctx.get("visits", 0)`), j'ai
   supposé que `EvaluationContext.get()` acceptait une valeur par défaut,
   comme `dict.get()`. Faux — Kimi ne l'avait pas implémenté ainsi. Le test
   échouait avec `Expected: 1, Actual: None`, ce qui ressemblait à un bug de
   persistance mais n'en était pas un : l'action de la règle levait une
   `TypeError` silencieusement absorbée par `rule_error_policy="continue"`,
   et mon test ne vérifiait pas `has_errors`. Trouvé en vérifiant
   directement `ctx.get("visits", 0)` avant d'accuser la mauvaise pièce. →
   `EvaluationContext.get(key, default=None)` — ajout rétrocompatible,
   attente naturelle pour quiconque connaît `dict.get()`.

**Ce qui reste ouvert**
- File d'attente des signaux dérivés (`max_derived_depth`) — toujours la
  seule priorité immédiate restante après ce tour.
- `duration_ms` non mesuré, `EngineConfig` comme dict privé plutôt que
  classe publique, `FactStore.query()` en O(n) global, aplatissement des AND
  chaînés — tous non bloquants, déjà notés.

**Fichiers concernés** : `_core.py`, `_context.py`, `_engine.py`, `__init__.py`

---

## 1er août 2026 (suite) — Revue de clôture (5 IA) : dérive de spec, préparation du gel v0.1.0

**Contexte** : ChatGPT, DeepSeek pro, Kimi et une nouvelle participante
(Meta IA, première apparition dans ce processus) valident les six
corrections du tour précédent. Aucune ne bloque la release. Meta IA fait en
plus une vérification section par section de `constitution-noyau.md` contre
le code réel.

**Résultat** : succès — deux dérives entre la spec et le code réel trouvées
et corrigées, aucune n'était un bug de comportement (le code avait raison,
la doc avait tort), plus une décision stratégique de séquencement.

**Problèmes rencontrés**

1. **`constitution-noyau.md` §2 décrivait `commit(version, causality)` et
   `__slots__ = ('entity_id', '_values', '_pending_effects')`.** → Trouvé
   par Meta IA en comparant section par section la spec au code livré. Le
   code réel de Kimi (`commit(causality, clock)`, version auto-incrémentée,
   `_pending_effects` jamais utilisé) est meilleur que ce que la spec
   décrivait encore — personne n'était retourné mettre à jour le texte après
   l'avoir validé en pratique. → Spec corrigée pour refléter le code qui
   tourne réellement, pas l'inverse.

2. **`slots=True` exige Python 3.10+.** → Meta IA a dû "patcher" le code
   pour le faire tourner sur Python 3.9. Vérifié : ce n'est pas un bug,
   `constitution-finale.md` §6 verrouille déjà 3.11+ — la bonne réponse
   n'est pas de baisser la compatibilité, c'est d'empêcher `pip install` de
   s'installer silencieusement sur un Python trop ancien. →
   `pyproject.toml` créé avec `requires-python = ">=3.11"`.

**Décision stratégique (recommandée par Kimi, retenue)** : ne pas coder la
file d'attente des signaux dérivés dans la foulée. C'est une vraie décision
d'architecture (`evaluate()` récursif ? risque de stack overflow ? un
`tick()` séparé ? synchrone ou non ?), pas une correction de bug — elle
mérite son propre tour multi-IA dédié, pas une fin de session fatiguée.
`_version.py` passé à `0.1.0-rc1` (pas encore `0.1.0` — en attente de la
confirmation explicite des 5 IA sur "bloquez-vous cette release ?").

**Ce qui reste ouvert** : file d'attente des signaux dérivés (tour dédié à
venir), `duration_ms`, `EngineConfig` comme classe publique, nom du package
encore un placeholder.

**Fichiers concernés** : `constitution-noyau.md`, `_version.py`, `pyproject.toml` (nouveau)

---

## 1er août 2026 (suite) — Renommage définitif : decisioncore → sinmonto

**Contexte** : après trois collisions de marque trouvées en une soirée
(DecisionCore™ — moteur de crédit déposé, Attest® + Attestify — logiciels
de conformité/audit déposés, Vigil — utilisé par au moins cinq entreprises
dont une avec un positionnement quasi identique au nôtre), exploration d'une
piste en fon (langue du Bénin). Verrouillé sur `sinmonto`, du fon *Sɛ́n
mɔto* — traduction officielle et grammaticalement correcte de "moteur de
règle", pas un mot inventé. Vérifié sans collision commerciale ou
logicielle : les seules occurrences trouvées sont des patronymes japonais
sans rapport.

**Résultat** : succès — renommage complet et vérifié, rien de cassé.

**Ce qui a été fait**
- Dossier du package : `decisioncore/` → `sinmonto/`.
- Toutes les occurrences textuelles dans le code et `pyproject.toml`
  remplacées (`sed`, puis vérification qu'il n'en reste aucune).
- `constitution-finale.md` et `constitution-noyau.md` mis à jour — la ligne
  "nom du package : placeholder, à verrouiller" (§6) devient la décision
  verrouillée avec sa justification.
- Suite de tests complète relancée après renommage, y compris l'import du
  package depuis l'extérieur et `test_end_to_end.py` : tout passe, rien de
  cassé par le changement de nom.

---

## 6 août 2026 — Revue croisée multi-IA (6 participants) : de rc1 à preview technique

**Contexte** : ChatGPT, Grok, DeepSeek, Kimi, Qwen et Meta AI ont chacune fait
une revue indépendante et statique du dépôt à l'état `0.1.0-rc1`, plus une
vérification directe du code par Claude (tests exécutés, fichiers lus ligne
par ligne, pas seulement les revues résumées). Objectif : décider si `rc1`
peut devenir une release publique, sous forme de preview technique plutôt
que d'attendre une v1.0 complète.

**Résultat** : succès — six bugs silencieux corrigés (ceux qui trahissaient
la promesse d'explicabilité/déterminisme, pas de simples trous documentés),
41 tests passent (modules + intégration), doc resynchronisée dans 7
fichiers. Deux propositions initiales de Claude se sont révélées fausses en
cours de route et ont été corrigées par le processus multi-IA lui-même —
gardé ci-dessous, c'est le genre d'erreur que ce journal existe pour ne pas
répéter.

**Problèmes rencontrés**

1. **Contrat public `Symbole` : jamais un bug, un placeholder de rédaction
   jamais rempli.** → Trouvé indépendamment par les six IA (unanimité rare),
   confirmé par Claude en lisant `__init__.py`/`CLAUDE.md`/`AGENTS.md`/les
   deux constitutions directement : le mot « Symbole » y apparaît tel quel,
   absent de `__all__` en pratique (`hasattr(sinmonto, "Symbole")` → False).
   → Plutôt que d'inventer un symbole unique a posteriori, la formulation
   remplacée partout par « les 37 noms de `__all__` sont le contrat public »
   — plus honnête vu le nombre d'exports réels.

2. **Copie superficielle du contexte : un `FrozenContext` déjà figé pouvait
   être corrompu rétroactivement.** → Trouvé indépendamment par plusieurs IA
   (le plus détaillé avec script de reproduction complet) : `commit()`
   faisait `self._values.copy()`, le rechargement de `previous.values` en
   cycle suivant faisait `dict(previous.values)` — les deux superficiels, un
   objet imbriqué (liste, dict) restait partagé entre deux `FrozenContext`.
   → `copy.deepcopy` aux deux endroits. Test de non-régression : mutation
   d'une liste après `commit()` ne change plus le `FrozenContext` stocké ;
   deuxième moteur sur le même `ContextStore`, mutation en place au cycle
   2 ne corrompt plus le `FrozenContext` du cycle 1.

3. **Atomicité des règles : `ctx.set()` direct avant un crash survivait au
   commit final — et la première correction proposée était fausse.** →
   Claude a d'abord proposé d'élargir `except Exception` à `BaseException`.
   Refusé par quasi-unanimité (Grok, Qwen, Meta AI, ChatGPT deux fois) —
   avaler `SystemExit`/`KeyboardInterrupt` est un anti-pattern Python
   reconnu. En creusant pourquoi le refus était juste, pas seulement
   majoritaire : élargir le type d'exception capturé ne change rien au
   problème visé, la mutation via `ctx.set()` a déjà eu lieu *avant* que
   l'exception ne soit levée, que le `except` attrape `Exception` ou
   `BaseException`. → `except Exception` inchangé. Vraie correction :
   snapshot (`deepcopy`) de `ctx._values` avant chaque `rule.evaluate()`,
   restauré si elle lève. Testé : une action qui fait `ctx.set("leaked",
   True)` puis plante ne laisse plus `"leaked"` dans le contexte stocké.

4. **`Signal.entity_id` explicite pouvait contredire `fact.entity_id` sans
   avertissement.** → Trouvé par ChatGPT : le moteur suit `signal.entity_id`
   pour l'évaluation pendant que le `Fact` reste stocké sous une autre
   entité — séparation silencieuse de contexte. → `Signal.__post_init__`
   lève `ValueError` si les deux sont fournis et diffèrent.

5. **Opérateur `FieldCondition` ou kind `CompositeCondition` invalide ne
   levait jamais rien.** → Trouvé par ChatGPT/Qwen/Kimi : un opérateur mal
   orthographié (`"gtt"`) évaluait silencieusement `False` pour toujours,
   nulle part une erreur — contraire à "fail loud" déjà promis en
   constitution. → Validation ajoutée dans `__post_init__` des deux classes,
   au moment le plus tôt possible (avant même `add_rule()`/`compile()`).

6. **Retour d'action non reconnu ignoré silencieusement ; retour direct
   d'`EvaluationResult` pouvait écraser la trace déjà calculée.** → Trouvé
   par ChatGPT (le premier cas), Qwen (le second, en posant la question :
   qui a le droit de muter le contexte si les règles ne doivent jamais
   avoir d'effet de bord ?). → `Rule.evaluate()` lève `InvalidEffectError`
   (existait, jamais utilisée jusqu'ici) sur un type non reconnu ou un
   retour `EvaluationResult` direct, désormais interdit.

7. **`Fact._payload` mutable après construction.** → Trouvé par Kimi/Qwen :
   le dict passé au constructeur restait partagé, une mutation externe après
   coup changeait le `Fact` malgré `frozen=True`. → Copie défensive dans
   `Fact.__post_init__`.

8. **`causality` vide pour un timer, incomplète pour un fait.** → Proposé
   par Claude, validé par toutes les IA sans réserve. → `(fact.fact_id,
   *fact.causality)` pour un fait, `(signal.signal_id,)` pour un timer.

9. **`InMemoryFactStore(max_facts=0)` plantait avec un `IndexError` obscur**
   (`deque(maxlen=0).popleft()` sur deque vide dès le premier `append()`).
   → Trouvé par DeepSeek et Qwen. → `ValueError` clair dans `__init__`.

10. **`_testing.py` sortait toujours avec le code 0, même avec des `FAIL`.**
    → Proposé par DeepSeek/Qwen. Premier essai (compteur d'échecs +
    `sys.exit(1)` dans un callback `atexit`) silencieusement inopérant —
    Python avale explicitement une exception levée dans un callback
    `atexit` ("Exception ignored in atexit callback"), vérifié en le
    testant en sous-process, pas supposé. → `os._exit(1)` après `flush()`
    explicite des flux, qui contourne le mécanisme d'exception. Revérifié :
    run propre → 0, run avec un échec délibéré → 1.

11. **Dérive doc/code étalée sur 7 fichiers** (`constitution-noyau.md` §1/§3/
    §4 : `condition_trace`, `Signal.entity_id` absent de la spec, kind
    `"none"`/`"error"` manquants, signature `index_rule` ; `pyproject.toml` :
    commentaire "nom jamais verrouillé" alors que `constitution-finale.md`
    §6 le verrouille depuis le renommage du 1er août ; licence encore "à
    trancher" en §6 alors que `LICENSE`/README l'ont déjà réglée en
    Apache-2.0 ; `README.md` : `test_end_to_end.py` inexistant, vrai chemin
    `examples/end_to_end.py`, jamais mis à jour après le renommage du
    fichier). → Chaque écart vérifié directement dans les fichiers réels
    avant correction (pas seulement sur la foi des revues) — un des
    reviewers avait travaillé sur un transcript abîmé et soulevé de faux
    doutes sur la validité du TOML et de `__all__`, écartés après lecture
    directe des fichiers.

12. **`CLAUDE.md` était une copie mot pour mot d'`AGENTS.md`**, avec encore
    le titre `# AGENTS.md` en ligne 1 — la preuve du copier-coller. → Trouvé
    par Qwen. → `CLAUDE.md` remplacé par un pointeur d'une ligne vers
    `AGENTS.md`, qui reste la seule source de vérité.

13. **Version : la justification initiale de Claude pour `0.1.0` nu était
    fausse.** → Claude a proposé de retirer `-rc1` et de publier `0.1.0` en
    citant le comportement PyPI des pre-releases comme garde-fou — mais
    `0.1.0` sans suffixe n'EST plus une pre-release, `pip install sinmonto`
    l'installerait par défaut sans `--pre`. Confusion signalée par Qwen,
    vérifiée : le raisonnement citait une règle PyPI réelle pour justifier
    une conclusion qu'elle ne soutenait pas. → `0.1.0rc2` retenu (reste en
    pre-release tant qu'il n'y a pas eu de retour d'usage externe réel), mot
    "preview" utilisé dans le README/l'annonce plutôt que dans le tag.

**Ce qui reste ouvert** — assumé, documenté, pas caché : file d'attente des
signaux dérivés (tour d'architecture dédié, toujours pas ce tour-ci),
`duration_ms` non mesuré, AND chaînés non aplatis dans la trace, pas de
politique de rétention sur les stores mémoire.

**Fichiers concernés** : `_core.py`, `_context.py`, `_dsl.py`, `_engine.py`,
`_exceptions.py`, `_testing.py`, `examples/end_to_end.py`, `__init__.py`,
`_version.py`, `pyproject.toml`, `constitution-finale.md`,
`constitution-noyau.md`, `README.md`, `AGENTS.md`, `CLAUDE.md`

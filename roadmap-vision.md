# Roadmap & Vision — hors scope v1.0

**Principe directeur** (posé par Clarel, à appliquer systématiquement) : à chaque décision, se demander *"est-ce que ça rapproche réellement la v1.0, ou est-ce qu'on rêve d'une fonctionnalité qui n'aura peut-être jamais besoin d'exister ?"* Si c'est la seconde réponse, ça va ici, jamais dans la Constitution du noyau.

---

## 1. Le second point d'entrée, noté pour plus tard

`engine.authorize(proposed_effect, context) -> Decision` — même mécanique que `evaluate()`, aucune nouvelle primitive (`Effect`/`Context`/`Evaluable` existent déjà dans le noyau). Coût d'ajout quasi nul quand le besoin sera réel. Retiré de la Constitution parce que rien dans la v1.0 n'en a besoin aujourd'hui.

## 2. Vision produit — la plateforme (après le noyau, après la traction)

Interface visuelle de construction de règles/états/transitions, avec :
- génération instantanée du Python équivalent et parité graphe ↔ code garantie par construction (un seul modèle d'objets canonique — `Rule`/`CompositeCondition`/`Effect` — le graphe et le code sont deux vues du même objet, pas deux formats à synchroniser)
- simulation, replay déterministe, trace d'explication affichée dans l'UI
- passage no-code ↔ code sans rupture, avec un nœud "code custom" opaque pour tout ce qui sort du sous-ensemble déclaratif du DSL

Précédent validé : DMN (norme OMG depuis 2015) est exactement cette idée en notation standardisée. Camunda (BPMN+DMN visuel + moteur + gouvernance) en a fait un vrai business.

## 3. Comparables business vérifiés (pour calibrer, pas pour décider maintenant)

- **Confluent** (Kafka) : 1 521 clients à 100k$+ ARR, 1,12 milliard $ de revenu d'abonnement — après 13 ans et une IPO.
- **Camunda** (BPMN/DMN) : 500+ clients enterprise, 250 000+ développeurs dans la communauté open-source — le ratio adoption→conversion à retenir.
- **Zapier** (no-code) : 3M+ utilisateurs, 100k+ payants, ~310-400M$ de revenu — plafond du category leader no-code après 14 ans.
- **Codex/ChatGPT Work** : ~10M utilisateurs actifs mi-2026, mais décrit par la presse elle-même comme "une croissance que la plupart des SaaS enterprise ne voient jamais" — anomalie explicitement nommée, pas base de planification.
- **Gouvernance d'agents IA** : vague réelle et datée (AI Act européen, application août 2026 ; 51% des organisations ont déjà des agents en prod mais 63% ne peuvent pas les limiter). Marché déjà formé, déjà concurrentiel (Arthur, Atlan, AWS Bedrock Guardrails), pas vide — mais créneau réel sur la décision métier profonde et explicable plutôt que le filtrage de sécurité générique que font ces acteurs.

## 4. Fonctionnalités notées

**Nouvelles**
- Policy Diffing & Impact Simulation (rejouer un changement de règle contre l'historique, chiffrer l'impact avant déploiement)
- Arbitrage multi-agents (résoudre des `Effect` conflictuels proposés par plusieurs agents)
- Compliance Certification Packs (rapports pré-mappés à des réglementations : AI Act, PCI-DSS, BCEAO/UEMOA)
- Decision Health (détection de dérive statistique)

**Renforcées**
- `AlphaIndex` palier riche (opérateur/valeur)
- Partitionnement distribué managé
- `StateBackend` hébergé/géré
- Replay contrefactuel en masse

**Groupées, par persona**
- Bundle Conformité : trace + replay + certification packs + console de gouvernance
- Bundle Gouvernance Agentique : `authorize()` + MCP + arbitrage multi-agents + policy diffing + decision health
- Bundle No-Code Métier : builder visuel + parité code + policies versionnées + console de gouvernance

## 5. Règle de retour

Rien ici n'est implémenté avant que le noyau v1.0 tourne réellement, avec un premier cas d'usage complet validé. On y revient à ce moment-là, pas avant.

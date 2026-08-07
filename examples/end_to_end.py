"""Exemple d'intégration bout-en-bout : DSL -> Engine -> Decision & Trace.

Exécutable directement depuis n'importe où dans le dépôt cloné :
    python3 examples/end_to_end.py
"""

import sys
from pathlib import Path

# Permet de lancer ce fichier directement (python3 examples/end_to_end.py)
# sans avoir installé le package — ajoute la racine du dépôt à sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from decimal import Decimal
from uuid import uuid4

# Imports depuis la surface publique officielle (__init__.py) — c'est le
# seul chemin d'import garanti (voir constitution-finale.md §8). Cet exemple
# utilise donc des `assert` simples plutôt que sinmonto._testing, qui est un
# module interne. Trouvé en revue (Qwen) — 2026-08.
from sinmonto import (
    DecisionEngine,
    Effect,
    Fact,
    Field,
    ManualClock,
    Signal,
    rule,
)


def run_full_integration_test():
    # 1. Initialisation de l'horloge et du moteur
    clock = ManualClock(Decimal("1700000000.0"))
    engine = DecisionEngine(clock=clock)

    # 2. Définition des règles via le DSL et le décorateur @rule
    # Règle 1 : Détection de gros montant pour compte standard (priorité haute)
    @rule(
        name="high_amount_alert",
        priority=100,
        condition=(Field("amount") > 1000) & (Field("vip") == False),
        engine=engine,
    )
    def check_high_amount(ctx, fact):
        # Action : produit un effet et enregistre une variable dans le contexte
        return [
            Effect("FLAG_TRANSACTION", {"reason": "high_amount_non_vip"}, "high_amount_alert"),
            {"risk_score": 0.85},
        ]

    # Règle 2 : Réduction automatique pour les membres VIP (priorité moyenne)
    @rule(
        name="vip_discount",
        priority=50,
        condition=Field("vip") == True,
        engine=engine,
    )
    def apply_vip_discount(ctx, fact):
        return Effect("APPLY_DISCOUNT", {"rate": 0.15}, "vip_discount")

    # Règle 3 : Règle défaillante pour tester l'isolation d'erreur (rule_error_policy="continue")
    @rule(
        name="buggy_rule",
        priority=10,
        condition=Field("amount") > 0,
        engine=engine,
    )
    def crash_action(ctx, fact):
        raise RuntimeError("Bug imprévu dans la logique métier")

    # 3. Verrouillage / Compilation de la configuration
    engine.compile()

    # 4. Préparation du Fait et du Signal d'entrée
    fact_data = Fact(
        fact_id=uuid4(),
        entity_id="usr_99",
        fact_type="payment",
        _payload={"amount": 2500, "vip": False},
        timestamp=clock.now(),
    )
    signal = Signal(
        signal_id=uuid4(),
        fact=fact_data,
        signal_type="payment_received",
        timestamp=clock.now(),
    )

    # 5. Évaluation du Signal par le moteur
    decision = engine.evaluate(signal)

    # -----------------------------------------------------------------------
    # Vérifications et Assertions
    # -----------------------------------------------------------------------

    # A. La décision globale signale qu'une erreur isolée est survenue
    assert decision.has_errors is True, "has_errors doit être True suite au crash de buggy_rule"

    # B. Les effets produits par la règle valide sont bien présents
    assert len(decision.effects) == 1, "Un seul effet valide doit être conservé"
    assert decision.effects[0].effect_type == "FLAG_TRANSACTION"
    assert decision.effects[0].payload["reason"] == "high_amount_non_vip"

    # C. Audit de la trace de décision (ordre d'évaluation respectant les priorités)
    trace = decision.trace
    assert trace.evaluation_order == ("high_amount_alert", "vip_discount", "buggy_rule")

    # D. Explicabilité : vérification de l'arbre de condition sur high_amount_alert
    rule1_trace = [t for t in trace.rule_traces if t.rule_id == "high_amount_alert"][0]
    assert rule1_trace.matched is True
    assert rule1_trace.condition_tree.kind == "and"
    assert rule1_trace.condition_tree.children[0].actual_value == 2500
    assert rule1_trace.condition_tree.children[1].actual_value is False

    # E. Explicabilité : vérification du court-circuit/échec sur vip_discount
    rule2_trace = [t for t in trace.rule_traces if t.rule_id == "vip_discount"][0]
    assert rule2_trace.matched is False
    assert rule2_trace.condition_tree.actual_value is False


if __name__ == "__main__":
    print("Exécution du test d'intégration bout-en-bout...")
    run_full_integration_test()
    print("  ok — cycle complet DSL -> Engine -> Decision & Trace")

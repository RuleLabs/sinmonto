"""Tests de non-régression — bugs trouvés en revue croisée multi-IA (rc2/rc3).

Chaque test porte en commentaire le bug d'origine et, quand c'est connu,
qui l'a trouvé. Voir docs/journal-integration.md pour le récit complet.
Ce fichier est la chronologie vivante de ce qui a déjà cassé — un nouveau
contributeur peut le lire sans passer par 500 lignes de journal.
"""

from __future__ import annotations

import base64
import json
import uuid
from decimal import Decimal

from sinmonto._core import Effect, EvaluationResult, Fact, Signal, _EngineJSONEncoder
from sinmonto._context import EvaluationContext, InMemoryContextStore, InMemoryFactStore
from sinmonto._dsl import CompositeCondition, Field, FieldCondition, Rule
from sinmonto._engine import DecisionEngine
from sinmonto._exceptions import InvalidConditionError, InvalidEffectError


def make_signal(payload: dict, entity_id: str = "e1") -> Signal:
    fact = Fact(
        fact_id=uuid.uuid4(), entity_id=entity_id, fact_type="transaction",
        _payload=payload, timestamp=Decimal("0"),
    )
    return Signal(signal_id=uuid.uuid4(), fact=fact, signal_type="transaction", timestamp=Decimal("0"))


class _TestClock:
    def __init__(self, value: Decimal) -> None:
        self._value = value

    def now(self) -> Decimal:
        return self._value


# --------------------------------------------------------------------------- #
# _core.py
# --------------------------------------------------------------------------- #

def test_fact_payload_defensive_copy() -> None:
    """Sans copie défensive, un appelant qui garde la référence au dict
    passé en _payload pouvait le muter après coup — trouvé par Kimi/Qwen."""
    original = {"amount": 100}
    f = Fact(
        fact_id=uuid.uuid4(), entity_id="user:1", fact_type="t",
        _payload=original, timestamp=Decimal("0"),
    )
    original["amount"] = 9999
    assert f.payload["amount"] == 100


def test_fact_payload_defensive_copy_is_deep() -> None:
    """La première copie défensive était superficielle (dict()) — une valeur
    imbriquée mutée après coup passait encore. Trouvé par ChatGPT/Grok
    au tour rc2 -> rc3."""
    original = {"items": [1, 2, 3]}
    f = Fact(
        fact_id=uuid.uuid4(), entity_id="user:1", fact_type="t",
        _payload=original, timestamp=Decimal("0"),
    )
    original["items"].append(999)
    assert f.payload["items"] == [1, 2, 3]


def test_effect_payload_is_protected() -> None:
    """Effect.payload n'avait aucune protection avant rc3 (ni copie, ni
    MappingProxyType) — trouvé par Grok."""
    original = {"reason": "x", "nested": [1, 2]}
    e = Effect(effect_type="ALERT", payload=original, rule_id="r1")
    original["reason"] = "changed"
    original["nested"].append(999)
    assert e.payload["reason"] == "x"
    assert e.payload["nested"] == [1, 2]
    try:
        e.payload["reason"] = "hack"  # type: ignore[index]
    except TypeError:
        pass
    else:
        raise AssertionError("Effect.payload devrait être en lecture seule")


def test_signal_entity_id_must_match_fact() -> None:
    """signal.entity_id explicite en désaccord avec fact.entity_id n'était
    pas détecté — le moteur suivait signal.entity_id en silence pendant que
    le Fact restait sous une autre entité. Trouvé par ChatGPT."""
    f = Fact(
        fact_id=uuid.uuid4(), entity_id="user:A", fact_type="t",
        _payload={}, timestamp=Decimal("0"),
    )
    try:
        Signal(
            signal_id=uuid.uuid4(), fact=f, signal_type="t",
            timestamp=Decimal("0"), entity_id="user:B",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("entity_id incohérent devrait lever ValueError")


# --------------------------------------------------------------------------- #
# _context.py
# --------------------------------------------------------------------------- #

def test_commit_protects_nested_values_via_deep_copy() -> None:
    """commit() faisait .copy() (superficiel) — une valeur imbriquée mutée
    après coup corrompait un FrozenContext déjà figé. Trouvé en revue
    croisée (Kimi le plus en détail, confirmé par ChatGPT/Qwen/Grok)."""
    ctx = EvaluationContext(entity_id="user_nested", base_version=0)
    nested_list = [1, 2, 3]
    ctx.set("items", nested_list)
    frozen = ctx.commit(causality=(), clock=_TestClock(Decimal("0")))
    nested_list.append(999)
    assert frozen.values["items"] == [1, 2, 3]


def test_inmemory_fact_store_rejects_zero_max() -> None:
    """InMemoryFactStore(max_facts=0) faisait planter le premier append()
    avec un IndexError obscur (deque(maxlen=0).popleft() sur deque vide).
    Trouvé par DeepSeek/Qwen."""
    try:
        InMemoryFactStore(max_facts=0)
    except ValueError:
        pass
    else:
        raise AssertionError("max_facts=0 devrait lever ValueError proprement")


# --------------------------------------------------------------------------- #
# _dsl.py
# --------------------------------------------------------------------------- #

def test_mixed_list_action_captures_dict_as_context_delta() -> None:
    """Un dict imbriqué dans une liste retournée par une action était
    silencieusement perdu au lieu d'alimenter context_delta."""
    r = Rule(
        "test", condition=None,
        action=lambda ctx, fact: [Effect("FLAG", {}, "test"), {"risk_score": 0.85}],
    )
    result = r.evaluate(ctx=None, fact=None)
    assert len(result.effects) == 1
    assert dict(result.context_delta) == {"risk_score": 0.85}


def test_field_condition_rejects_unknown_operator() -> None:
    """Un opérateur mal orthographié ("gtt") évaluait silencieusement False
    pour toujours, sans jamais rien lever. Trouvé par ChatGPT/Qwen/Kimi."""
    try:
        FieldCondition("amount", "gtt", 100)
    except InvalidConditionError:
        pass
    else:
        raise AssertionError("opérateur inconnu devrait lever InvalidConditionError")


def test_composite_condition_rejects_unknown_kind() -> None:
    """Un kind inconnu ("xor") ne levait ValueError qu'à evaluate(), trop
    tard pour le "fail loud à la compilation" promis. Trouvé par Qwen."""
    try:
        CompositeCondition("xor", (Field("a") == 1,))
    except InvalidConditionError:
        pass
    else:
        raise AssertionError("kind inconnu devrait lever InvalidConditionError")


def test_rule_action_rejects_unrecognized_return_type() -> None:
    """Un retour d'action non reconnu (int, str...) était silencieusement
    ignoré — matched=True mais 0 effet, sans trace ni erreur. Trouvé par
    ChatGPT."""
    r = Rule("bad_return", condition=None, action=lambda ctx, fact: 42)
    try:
        r.evaluate(ctx=None, fact=None)
    except InvalidEffectError:
        pass
    else:
        raise AssertionError("retour non reconnu devrait lever InvalidEffectError")


def test_rule_action_rejects_evaluation_result_direct_return() -> None:
    """Un retour EvaluationResult direct pouvait écraser le condition_trace
    déjà calculé par la règle — deuxième voie de mutation non tracée.
    Trouvé par Qwen."""
    r = Rule(
        "bad_shortcut", condition=None,
        action=lambda ctx, fact: EvaluationResult(
            matched=True, effects=(), derived_signals=(),
            context_delta={}, condition_trace=None,
        ),
    )
    try:
        r.evaluate(ctx=None, fact=None)
    except InvalidEffectError:
        pass
    else:
        raise AssertionError("EvaluationResult direct devrait lever InvalidEffectError")


# --------------------------------------------------------------------------- #
# _engine.py
# --------------------------------------------------------------------------- #

def test_add_rule_rejects_invalid_condition_type() -> None:
    """condition="oops" laissait fuir une AttributeError brute plus tard
    au lieu d'un échec clair à l'enregistrement. Trouvé par ChatGPT."""
    engine = DecisionEngine()
    try:
        engine.add_rule(Rule("bad", condition="oops", action=lambda ctx, fact: None))
    except InvalidConditionError:
        pass
    else:
        raise AssertionError("condition invalide devrait lever InvalidConditionError")


def test_tie_breaking_is_deterministic_across_many_runs() -> None:
    """AlphaIndex.match() retournait un set, dont l'ordre dépend du hash
    randomization de Python — le tie-breaking par ordre d'insertion n'était
    pas garanti. Trouvé par Kimi/DeepSeek. Répété 20 fois pour couvrir
    plusieurs seeds de hash."""
    for _ in range(20):
        engine = DecisionEngine()
        engine.add_rule(Rule("r1", priority=5, condition=None,
                              action=lambda ctx, fact: Effect("e1", {}, "r1")))
        engine.add_rule(Rule("r2", priority=5, condition=None,
                              action=lambda ctx, fact: Effect("e2", {}, "r2")))
        engine.add_rule(Rule("r3", priority=5, condition=None,
                              action=lambda ctx, fact: Effect("e3", {}, "r3")))
        engine.compile()
        decision = engine.evaluate(make_signal({"x": 1}))
        assert decision.trace.evaluation_order == ("r1", "r2", "r3")


def test_ctx_set_before_crash_does_not_survive_commit() -> None:
    """Une action qui fait ctx.set() directement puis plante laissait sa
    mutation survivre au commit final, quelle que soit rule_error_policy —
    violait la promesse "tout ou rien". Corrigé par snapshot/restore de
    ctx._values autour de chaque rule.evaluate(). Trouvé en revue croisée
    (Kimi, Grok, Qwen, Meta AI)."""
    def leaky_crash(ctx, fact) -> None:
        ctx.set("leaked", True)
        raise RuntimeError("boom")

    engine = DecisionEngine()
    engine.add_rule(Rule("leaky", priority=1, condition=None, action=leaky_crash))
    engine.compile()

    decision = engine.evaluate(make_signal({"x": 1}, "e_leak"))
    assert decision.has_errors is True
    stored = engine._context_store.get_latest("e_leak")
    assert "leaked" not in stored.values


def test_causality_chains_fact_id_or_signal_id() -> None:
    """causality était vide pour un timer, et fact.causality seul (sans
    fact.fact_id) pour un fait — perdait l'origine immédiate dans les deux
    cas. Verrouillé en revue croisée."""
    engine = DecisionEngine()
    engine.add_rule(Rule("noop", condition=None, action=lambda ctx, fact: None))
    engine.compile()

    sig = make_signal({"x": 1}, "e_causal")
    engine.evaluate(sig)
    stored = engine._context_store.get_latest("e_causal")
    assert stored.causality == (sig.fact.fact_id, *sig.fact.causality)

    timer_sig = Signal(
        signal_id=uuid.uuid4(), fact=None, signal_type="timer",
        timestamp=Decimal("0"), entity_id="e_causal",
    )
    engine.evaluate(timer_sig)
    stored2 = engine._context_store.get_latest("e_causal")
    assert stored2.causality == (timer_sig.signal_id,)


def test_reload_of_previous_context_is_deep_copied() -> None:
    """Le rechargement de previous.values au cycle suivant faisait dict()
    (superficiel) — une mutation en place d'une valeur imbriquée par une
    règle d'un cycle ultérieur corrompait rétroactivement le FrozenContext
    du cycle précédent. Trouvé par Qwen/Kimi."""
    shared_store = InMemoryContextStore()

    engine1 = DecisionEngine(context_store=shared_store)
    engine1.add_rule(Rule(
        "set_items", priority=10, condition=None,
        action=lambda ctx, fact: [{"items": [1, 2, 3]}],
    ))
    engine1.compile()
    engine1.evaluate(make_signal({"x": 1}, "e_reload"))
    frozen1 = shared_store.get_latest("e_reload")
    assert frozen1.values["items"] == [1, 2, 3]

    def mutate_in_place(ctx, fact) -> None:
        ctx.get("items").append(999)

    engine2 = DecisionEngine(context_store=shared_store)
    engine2.add_rule(Rule("mutate", priority=10, condition=None, action=mutate_in_place))
    engine2.compile()
    engine2.evaluate(make_signal({"x": 2}, "e_reload"))

    assert frozen1.values["items"] == [1, 2, 3]


# --------------------------------------------------------------------------- #
# Revue adversariale — Grok, benchmark rc4 (2026-09)
# --------------------------------------------------------------------------- #

def test_alpha_index_not_condition_matches_on_absent_field() -> None:
    """~(Field("vip") == True) doit matcher quand "vip" est absent du fait
    (la condition elle-même vaut True dans ce cas) — mais AlphaIndex
    indexait ce NOT comme n'importe quel champ positif : la règle ne
    devenait candidate QUE si "vip" est présent, donc n'était jamais
    évaluée dans exactement le cas où elle doit matcher. Silencieux :
    evaluation_order restait vide, aucune erreur. Violation du contrat
    d'AlphaIndex (constitution-noyau.md §4 : "un sur-ensemble de
    candidates, jamais un sous-ensemble"). Trouvé par Grok (test
    adversarial, benchmark rc4)."""
    engine = DecisionEngine()
    engine.add_rule(Rule(
        "not_vip", priority=1, condition=~(Field("vip") == True),
        action=lambda ctx, fact: Effect("FLAGGED", {}, "not_vip"),
    ))
    engine.compile()

    decision = engine.evaluate(make_signal({"amount": 10}))  # pas de "vip"
    assert "not_vip" in decision.trace.evaluation_order
    assert decision.effects and decision.effects[0].effect_type == "FLAGGED"


def test_fact_store_duplicate_fact_id_does_not_corrupt_eviction() -> None:
    """Un même fact_id ajouté deux fois (ex. redélivrance amont
    "at-least-once") créait deux entrées dans _order pour une seule dans
    _facts. La première éviction du fact_id fait `del self._facts[oldest]` ;
    la seconde position dans _order pointe alors vers un id absent de
    _facts, et query() levait KeyError — sur n'importe quelle entité, pas
    seulement celle du doublon, puisque query() résout `self._facts[fid]`
    avant de filtrer par entity_id. Trouvé par Grok (test adversarial,
    benchmark rc4)."""
    store = InMemoryFactStore(max_facts=3)
    dup = Fact(fact_id=uuid.uuid4(), entity_id="e1", fact_type="t", _payload={}, timestamp=Decimal("0"))
    store.append(dup)
    store.append(dup)  # même fact_id, redélivré
    for _ in range(3):
        store.append(Fact(fact_id=uuid.uuid4(), entity_id="e1", fact_type="t",
                           _payload={}, timestamp=Decimal("0")))
    store.query("e1")  # ne doit pas lever KeyError


def test_json_encoder_handles_non_utf8_bytes() -> None:
    """_EngineJSONEncoder décodait bytes en UTF-8 directement — levait
    UnicodeDecodeError sur des octets qui ne sont pas du texte UTF-8 valide
    (données binaires arbitraires, ex. un blob chiffré). base64 encode
    n'importe quelle séquence d'octets sans jamais lever. Trouvé par Grok
    (test adversarial, benchmark rc4)."""
    non_utf8 = b"\xff\xfe\x00\x01"
    encoded = json.dumps({"blob": non_utf8}, cls=_EngineJSONEncoder)
    parsed = json.loads(encoded)
    assert parsed["blob"]["__type"] == "bytes"
    assert base64.b64decode(parsed["blob"]["value"]) == non_utf8

"""Tests nominaux pour sinmonto._context — contexte à deux phases, stores."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from sinmonto._context import EvaluationContext, InMemoryContextStore, InMemoryFactStore
from sinmonto._core import Fact


class _TestClock:
    def __init__(self, value: Decimal) -> None:
        self._value = value

    def now(self) -> Decimal:
        return self._value


def test_commit_produces_correct_frozen_context() -> None:
    clock = _TestClock(Decimal("1234.567"))
    entity_id = "user_42"
    causality = (uuid4(), uuid4())

    ctx = EvaluationContext(entity_id=entity_id, base_version=5)
    ctx.set("score", Decimal("0.85"))
    ctx.set("status", "flagged")
    ctx.set("count", 3)

    frozen = ctx.commit(causality=causality, clock=clock)

    assert frozen.entity_id == entity_id
    assert frozen.version == 6
    assert frozen.timestamp == Decimal("1234.567")
    assert frozen.causality == causality
    assert frozen.values["score"] == Decimal("0.85")
    assert frozen.values["status"] == "flagged"
    assert frozen.values["count"] == 3


def test_frozen_values_reject_external_mutation() -> None:
    ctx = EvaluationContext(entity_id="e1")
    ctx.set("score", Decimal("0.85"))
    frozen = ctx.commit(causality=(), clock=_TestClock(Decimal("0")))
    try:
        frozen.values["score"] = Decimal("0.99")  # type: ignore[index]
    except TypeError:
        pass
    else:
        raise AssertionError("La mutation de frozen.values devrait lever TypeError")


def test_post_commit_mutation_does_not_affect_frozen() -> None:
    ctx = EvaluationContext(entity_id="e1")
    ctx.set("score", Decimal("0.85"))
    frozen = ctx.commit(causality=(), clock=_TestClock(Decimal("0")))
    ctx.set("score", Decimal("0.10"))
    assert frozen.values["score"] == Decimal("0.85")


def test_get_with_default() -> None:
    ctx = EvaluationContext(entity_id="e1")
    ctx.set("score", Decimal("0.10"))
    assert ctx.get("score") == Decimal("0.10")
    assert ctx.get("missing") is None
    assert ctx.get("missing", "fallback") == "fallback"


def test_inmemory_fact_store_basic() -> None:
    store = InMemoryFactStore(max_facts=3)
    f1 = Fact(
        fact_id=uuid4(), entity_id="e1", fact_type="tx",
        _payload={"amount": 100}, timestamp=Decimal("1.0"),
    )
    f2 = Fact(
        fact_id=uuid4(), entity_id="e1", fact_type="tx",
        _payload={"amount": 200}, timestamp=Decimal("2.0"),
    )
    store.append(f1)
    store.append(f2)
    assert store.get(f1.fact_id) is f1
    assert len(store.query("e1")) == 2
    assert len(store.query("e1", since=Decimal("2.0"))) == 1


def test_frozen_context_explicitly_non_hashable() -> None:
    ctx = EvaluationContext(entity_id="e1")
    ctx.set("score", Decimal("0.85"))
    frozen = ctx.commit(causality=(), clock=_TestClock(Decimal("0")))
    try:
        hash(frozen)
    except TypeError:
        pass
    else:
        raise AssertionError("FrozenContext ne devrait pas être hashable")


def test_context_store_persists_by_entity() -> None:
    clock = _TestClock(Decimal("0"))
    ctx = EvaluationContext(entity_id="user_42", base_version=5)
    ctx.set("score", Decimal("0.85"))
    frozen = ctx.commit(causality=(uuid4(),), clock=clock)

    cstore = InMemoryContextStore()
    assert cstore.get_latest("user_42") is None
    cstore.save(frozen)
    retrieved = cstore.get_latest("user_42")
    assert retrieved is frozen
    assert cstore.get_latest("autre_entite") is None

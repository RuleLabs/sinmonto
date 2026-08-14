"""Tests nominaux pour sinmonto._core — objets fondamentaux."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal

from sinmonto._core import Fact, ManualClock, Signal, _EngineJSONEncoder


def test_fact_payload_is_read_only() -> None:
    f = Fact(
        fact_id=uuid.uuid4(),
        entity_id="user:1",
        fact_type="transaction",
        _payload={"amount": 1500},
        timestamp=Decimal("0"),
    )
    assert f.payload["amount"] == 1500
    try:
        f.payload["amount"] = 9999  # type: ignore[index]
    except TypeError:
        pass
    else:
        raise AssertionError("payload should be read-only")


def test_manual_clock() -> None:
    clock = ManualClock(Decimal("100"))
    assert clock.now() == Decimal("100")
    clock.set(Decimal("200"))
    assert clock.now() == Decimal("200")


def test_json_encoder_handles_decimal_and_uuid() -> None:
    uid = uuid.uuid4()
    encoded = json.dumps({"amount": Decimal("10.5"), "id": uid}, cls=_EngineJSONEncoder)
    assert json.loads(encoded)["amount"]["value"] == "10.5"
    assert json.loads(encoded)["id"]["value"] == str(uid)


def test_signal_entity_id_derived_from_fact() -> None:
    f = Fact(
        fact_id=uuid.uuid4(), entity_id="user:42", fact_type="t",
        _payload={}, timestamp=Decimal("0"),
    )
    s = Signal(signal_id=uuid.uuid4(), fact=f, signal_type="t", timestamp=Decimal("0"))
    assert s.entity_id == "user:42"


def test_signal_requires_explicit_entity_id_without_fact() -> None:
    try:
        Signal(signal_id=uuid.uuid4(), fact=None, signal_type="timer", timestamp=Decimal("0"))
    except ValueError:
        pass
    else:
        raise AssertionError("un signal timer sans entity_id explicite devrait lever")

    s = Signal(
        signal_id=uuid.uuid4(), fact=None, signal_type="timer",
        timestamp=Decimal("0"), entity_id="user:99",
    )
    assert s.entity_id == "user:99"

"""Tests pour la hiérarchie d'exceptions (sinmonto._exceptions)."""

from __future__ import annotations

import uuid

from sinmonto._exceptions import (
    BackendError,
    EngineAlreadyCompiledError,
    EngineConfigurationError,
    EngineError,
    EngineNotCompiledError,
    EngineRuntimeError,
    MaxDerivedDepthExceededError,
    RuleEvaluationError,
)


def test_exceptions_hierarchy() -> None:
    assert issubclass(EngineNotCompiledError, EngineConfigurationError)
    assert issubclass(EngineAlreadyCompiledError, EngineConfigurationError)
    assert issubclass(EngineConfigurationError, EngineError)
    assert issubclass(RuleEvaluationError, EngineRuntimeError)
    assert issubclass(EngineRuntimeError, EngineError)
    assert issubclass(BackendError, EngineError)
    assert issubclass(MaxDerivedDepthExceededError, EngineRuntimeError)


def test_max_derived_depth_exceeded_error_carries_context() -> None:
    sig_id = uuid.uuid4()
    try:
        raise MaxDerivedDepthExceededError(signal_id=sig_id, depth=4, max_depth=3)
    except MaxDerivedDepthExceededError as e:
        assert e.signal_id == sig_id
        assert e.depth == 4
        assert e.max_depth == 3


def test_rule_evaluation_error_carries_cause_and_rule_id() -> None:
    original = ValueError("boom")
    try:
        raise RuleEvaluationError("r1", original, "sig-123")  # type: ignore[arg-type]
    except RuleEvaluationError as e:
        assert e.rule_id == "r1"
        assert e.__cause__ is original

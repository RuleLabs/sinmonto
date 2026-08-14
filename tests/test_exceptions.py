"""Tests pour la hiérarchie d'exceptions (sinmonto._exceptions)."""

from __future__ import annotations

from sinmonto._exceptions import (
    BackendError,
    EngineAlreadyCompiledError,
    EngineConfigurationError,
    EngineError,
    EngineNotCompiledError,
    EngineRuntimeError,
    RuleEvaluationError,
)


def test_exceptions_hierarchy() -> None:
    assert issubclass(EngineNotCompiledError, EngineConfigurationError)
    assert issubclass(EngineAlreadyCompiledError, EngineConfigurationError)
    assert issubclass(EngineConfigurationError, EngineError)
    assert issubclass(RuleEvaluationError, EngineRuntimeError)
    assert issubclass(EngineRuntimeError, EngineError)
    assert issubclass(BackendError, EngineError)


def test_rule_evaluation_error_carries_cause_and_rule_id() -> None:
    original = ValueError("boom")
    try:
        raise RuleEvaluationError("r1", original, "sig-123")  # type: ignore[arg-type]
    except RuleEvaluationError as e:
        assert e.rule_id == "r1"
        assert e.__cause__ is original

"""Hiérarchie d'exceptions du moteur.

Racine du graphe de dépendances internes — ce module n'importe rien d'autre
de sinmonto, pour que tous les autres modules puissent l'importer sans
jamais créer de cycle.
"""

from __future__ import annotations

from uuid import UUID


class EngineError(Exception):
    """Base de toutes les exceptions du moteur."""


class EngineConfigurationError(EngineError):
    """Erreurs détectées à compile() ou add_rule() — fail loud, systématique."""


class EngineNotCompiledError(EngineConfigurationError):
    """Tentative d'évaluer avant que compile() ait été appelé."""


class EngineAlreadyCompiledError(EngineConfigurationError):
    """Tentative de modifier la configuration après compile()."""


class DuplicateRuleError(EngineConfigurationError):
    """Une règle avec ce rule_id est déjà enregistrée."""


class InvalidConditionError(EngineConfigurationError):
    """Condition invalide détectée à la compilation."""


class InvalidEffectError(EngineConfigurationError):
    """Effet mal formé détecté à l'enregistrement d'une règle."""


class EngineRuntimeError(EngineError):
    """Erreurs pendant evaluate() — comportement gouverné par rule_error_policy."""


class RuleEvaluationError(EngineRuntimeError):
    """Encapsule une exception levée dans le evaluate() d'une règle."""

    def __init__(self, rule_id: str, original: Exception, signal_id: UUID) -> None:
        self.rule_id = rule_id
        self.signal_id = signal_id
        super().__init__(f"Rule '{rule_id}' crashed on signal {signal_id}: {original}")
        self.__cause__ = original


class ContextCorruptionError(EngineRuntimeError):
    """Un commit() a produit un état incohérent."""


class ClockError(EngineRuntimeError):
    """Temps injecté invalide ou non monotone."""


class BackendError(EngineError):
    """Erreurs des adaptateurs de persistance (StateBackend).

    Défini ici pour que le contrat existe, mais les implémentations concrètes
    vivent hors du cœur (adaptateurs séparés).
    """


if __name__ == "__main__":
    assert issubclass(EngineNotCompiledError, EngineConfigurationError)
    assert issubclass(EngineAlreadyCompiledError, EngineConfigurationError)
    assert issubclass(EngineConfigurationError, EngineError)
    assert issubclass(RuleEvaluationError, EngineRuntimeError)
    assert issubclass(EngineRuntimeError, EngineError)
    assert issubclass(BackendError, EngineError)

    original = ValueError("boom")
    try:
        raise RuleEvaluationError("r1", original, "sig-123")  # type: ignore[arg-type]
    except RuleEvaluationError as e:
        assert e.rule_id == "r1"
        assert e.__cause__ is original

    print("_exceptions.py: ok")

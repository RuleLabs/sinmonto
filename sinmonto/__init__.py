"""sinmonto — moteur de décision événementiel, explicable, en Python pur.

Surface publique garantie : les 37 noms listés dans `__all__` ci-dessous,
importables via `from sinmonto import <nom>`. Tout le reste (fichiers
préfixés _) est interne et peut changer sans préavis entre versions
mineures — voir constitution-finale.md §8.

(Avant 0.1.0-preview, ce docstring et la constitution promettaient un
symbole unique appelé « Symbole » comme seul contrat garanti — un
placeholder jamais rempli, absent de __all__ en pratique. Corrigé : avec
37 exports, prétendre à un symbole unique était une fiction plutôt qu'un
contrat vérifiable. Trouvé en revue croisée multi-IA — 2026-08.)
"""

from ._version import __version__
from ._exceptions import (
    BackendError,
    ClockError,
    ContextCorruptionError,
    DuplicateRuleError,
    EngineAlreadyCompiledError,
    EngineConfigurationError,
    EngineError,
    EngineNotCompiledError,
    EngineRuntimeError,
    InvalidConditionError,
    InvalidEffectError,
    RuleEvaluationError,
)
from ._core import (
    Clock,
    Decision,
    Effect,
    Evaluable,
    EvaluationResult,
    Fact,
    ManualClock,
    Signal,
)
from ._context import (
    ContextStore,
    EvaluationContext,
    FactStore,
    FrozenContext,
    InMemoryContextStore,
    InMemoryFactStore,
)
from ._trace import ConditionTrace, DecisionTrace, RuleTrace
from ._dsl import CompositeCondition, Field, FieldCondition, Rule, rule
from ._engine import AlphaIndex, DecisionEngine

__all__ = [
    "__version__",
    # Exceptions
    "EngineError",
    "EngineConfigurationError",
    "EngineNotCompiledError",
    "EngineAlreadyCompiledError",
    "DuplicateRuleError",
    "InvalidConditionError",
    "InvalidEffectError",
    "EngineRuntimeError",
    "RuleEvaluationError",
    "ContextCorruptionError",
    "ClockError",
    "BackendError",
    # Core
    "Clock",
    "ManualClock",
    "Fact",
    "Signal",
    "Effect",
    "Evaluable",
    "EvaluationResult",
    "Decision",
    # Context
    "EvaluationContext",
    "FrozenContext",
    "FactStore",
    "InMemoryFactStore",
    "ContextStore",
    "InMemoryContextStore",
    # Trace
    "ConditionTrace",
    "RuleTrace",
    "DecisionTrace",
    # DSL
    "Field",
    "FieldCondition",
    "CompositeCondition",
    "Rule",
    "rule",
    # Engine
    "AlphaIndex",
    "DecisionEngine",
]

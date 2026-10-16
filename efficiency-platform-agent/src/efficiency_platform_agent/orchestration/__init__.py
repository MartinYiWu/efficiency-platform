"""统一图运行时、Run 生命周期与 Checkpoint 协调。"""

from .cancellation import InMemoryCancellationSignal
from .contracts import CheckpointView, GraphExecutionResult, GraphRegistration
from .intent_interpreter import (
    IntentExecution,
    IntentInterpretationError,
    IntentInterpreter,
    IntentModelRuntime,
)
from .registry import GraphRegistry
from .runtime import GraphRuntime

__all__ = [
    "CheckpointView",
    "GraphExecutionResult",
    "GraphRegistration",
    "GraphRegistry",
    "GraphRuntime",
    "InMemoryCancellationSignal",
    "IntentExecution",
    "IntentInterpretationError",
    "IntentInterpreter",
    "IntentModelRuntime",
    "ResolvedScenarioCondition",
    "ScenarioResolution",
    "ScenarioResolver",
]


def __getattr__(name: str):
    if name in {
        "ResolvedScenarioCondition",
        "ScenarioResolution",
        "ScenarioResolver",
    }:
        from . import scenario_resolver

        return getattr(scenario_resolver, name)
    raise AttributeError(name)

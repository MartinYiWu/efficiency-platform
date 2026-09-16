"""Supervisor-led multi-Agent strategy with specialist subgraphs."""

from .executor import OperationSupervisorExecutor
from .nodes import SupervisorDependencies

__all__ = ["OperationSupervisorExecutor", "SupervisorDependencies"]

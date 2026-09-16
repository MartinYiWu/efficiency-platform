from __future__ import annotations

import ast
import importlib
import inspect
import sys
import unittest
from dataclasses import FrozenInstanceError, fields, is_dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


class CoreContractsTest(unittest.TestCase):
    def test_run_statuses_cover_complete_execution_lifecycle(self) -> None:
        from efficiency_platform_agent.core.enums import RunStatus

        self.assertEqual(
            {status.value for status in RunStatus},
            {
                "created",
                "queued",
                "running",
                "waiting_tool",
                "waiting_approval",
                "waiting_input",
                "succeeded",
                "failed",
                "cancelled",
                "timed_out",
            },
        )

    def test_strategy_modes_cover_hybrid_multi_agent_execution(self) -> None:
        from efficiency_platform_agent.core.enums import StrategyMode

        self.assertEqual(
            {mode.value for mode in StrategyMode},
            {
                "direct",
                "workflow",
                "react",
                "plan_execute",
                "multi_agent",
            },
        )

    def test_core_exposes_framework_neutral_extension_ports(self) -> None:
        from efficiency_platform_agent.core.ports import (
            AgentPlugin,
            ModelProvider,
            StrategyExecutor,
            Tool,
        )

        for port in (AgentPlugin, ModelProvider, StrategyExecutor, Tool):
            with self.subTest(port=port.__name__):
                self.assertTrue(getattr(port, "_is_protocol", False))

    def test_stable_core_boundaries_do_not_use_any(self) -> None:
        for relative_path in (
            "efficiency_platform_agent/core/run.py",
            "efficiency_platform_agent/core/ports.py",
        ):
            with self.subTest(path=relative_path):
                source_path = SRC_ROOT / relative_path
                tree = ast.parse(source_path.read_text(encoding="utf-8"))
                imported_any = any(
                    isinstance(node, ast.ImportFrom)
                    and node.module == "typing"
                    and any(alias.name == "Any" for alias in node.names)
                    for node in ast.walk(tree)
                )
                referenced_any = any(
                    isinstance(node, ast.Name) and node.id == "Any"
                    for node in ast.walk(tree)
                )
                self.assertFalse(imported_any or referenced_any)

    def test_controlled_json_values_reject_mutable_or_non_json_values(self) -> None:
        run_module = importlib.import_module("efficiency_platform_agent.core.run")
        JsonObject = self._require_type(run_module, "JsonObject")

        value = JsonObject((('query', ('alpha', 1, True, None)),))
        self.assertEqual(value.items[0][0], "query")
        with self.assertRaises(TypeError):
            JsonObject((('bad', ["mutable"]),))
        with self.assertRaises(TypeError):
            JsonObject((('bad', {"mutable": "mapping"}),))
        with self.assertRaises(TypeError):
            JsonObject([('bad_container', "mutable")])
        with self.assertRaises(ValueError):
            JsonObject((('duplicate', 1), ('duplicate', 2)))
        with self.assertRaises(ValueError):
            JsonObject((('not_finite', float("inf")),))

    def test_execution_budget_is_immutable_and_validated(self) -> None:
        run_module = importlib.import_module("efficiency_platform_agent.core.run")
        ExecutionBudget = self._require_type(run_module, "ExecutionBudget")
        budget = ExecutionBudget(
            max_iterations=3,
            max_tool_calls=2,
            max_input_tokens=100,
            max_output_tokens=50,
            timeout_ms=1_000,
            max_cost_microunits=25,
        )

        self._assert_frozen_slots_dataclass(budget)
        with self.assertRaises(FrozenInstanceError):
            budget.max_iterations = 4
        for field_name, invalid_value in (
            ("max_iterations", 0),
            ("max_tool_calls", -1),
            ("max_input_tokens", -1),
            ("max_output_tokens", -1),
            ("timeout_ms", 0),
            ("max_cost_microunits", -1),
        ):
            values = {
                "max_iterations": 3,
                "max_tool_calls": 2,
                "max_input_tokens": 100,
                "max_output_tokens": 50,
                "timeout_ms": 1_000,
                "max_cost_microunits": 25,
            }
            values[field_name] = invalid_value
            with self.subTest(field=field_name), self.assertRaises(ValueError):
                ExecutionBudget(**values)

    def test_extension_descriptor_is_versioned_and_fail_closed(self) -> None:
        run_module = importlib.import_module("efficiency_platform_agent.core.run")
        ExecutionBudget = self._require_type(run_module, "ExecutionBudget")
        ExtensionDescriptor = self._require_type(run_module, "ExtensionDescriptor")
        budget = self._budget(ExecutionBudget)
        descriptor = ExtensionDescriptor(
            name="research_agent",
            semantic_version="1.2.3",
            input_schema_version="task-input/1",
            output_schema_version="task-output/1",
            permissions=frozenset({"public_web.read"}),
            budget=budget,
            termination_conditions=frozenset({"succeeded", "failed"}),
            checkpoint_version="checkpoint/1",
        )

        self._assert_frozen_slots_dataclass(descriptor)
        self.assertEqual(descriptor.permissions, frozenset({"public_web.read"}))
        with self.assertRaises(ValueError):
            ExtensionDescriptor(
                name="research_agent",
                semantic_version="v1",
                input_schema_version="task-input/1",
                output_schema_version="task-output/1",
                permissions=frozenset(),
                budget=budget,
                termination_conditions=frozenset({"succeeded"}),
                checkpoint_version="checkpoint/1",
            )
        with self.assertRaises(ValueError):
            ExtensionDescriptor(
                name="research_agent",
                semantic_version="1.0.0",
                input_schema_version="task-input/1",
                output_schema_version="task-output/1",
                permissions=frozenset(),
                budget=budget,
                termination_conditions=frozenset(),
                checkpoint_version="checkpoint/1",
            )

    def test_supervisor_task_contains_only_trimmed_subtask_context(self) -> None:
        run_module = importlib.import_module("efficiency_platform_agent.core.run")
        ExecutionBudget = self._require_type(run_module, "ExecutionBudget")
        JsonObject = self._require_type(run_module, "JsonObject")
        SupervisorTask = self._require_type(run_module, "SupervisorTask")
        task = SupervisorTask(
            task_id="task-1",
            parent_run_id="run-1",
            target_agent="research_agent",
            input_data=JsonObject((('question', 'example'),)),
            context_view=JsonObject((('evidence_ids', ('e-1',)),)),
            allowed_tools=frozenset({"public_search"}),
            budget=self._budget(ExecutionBudget),
        )

        self._assert_frozen_slots_dataclass(task)
        self.assertEqual(
            {field.name for field in fields(task)},
            {
                "task_id",
                "parent_run_id",
                "target_agent",
                "input_data",
                "context_view",
                "allowed_tools",
                "budget",
            },
        )
        self.assertNotIn("user_id", {field.name for field in fields(task)})
        self.assertNotIn("input_text", {field.name for field in fields(task)})

    def test_tool_contract_is_versioned_structured_and_bounded(self) -> None:
        run_module = importlib.import_module("efficiency_platform_agent.core.run")
        required_types = (
            "ApprovalBinding",
            "JsonObject",
            "ToolError",
            "ToolRequest",
            "ToolResult",
        )
        resolved = {name: self._require_type(run_module, name) for name in required_types}
        request_fields = {field.name for field in fields(resolved["ToolRequest"])}
        result_fields = {field.name for field in fields(resolved["ToolResult"])}

        self.assertTrue(
            {
                "contract_version",
                "tool_name",
                "arguments",
                "timeout_ms",
                "approval_binding",
                "idempotency_key",
                "has_side_effects",
                "max_output_bytes",
            }.issubset(request_fields)
        )
        self.assertTrue(
            {
                "contract_version",
                "output",
                "error",
                "output_bytes",
                "is_truncated",
            }.issubset(result_fields)
        )
        binding = resolved["ApprovalBinding"](
            approval_id="approval-1",
            subject_id="user-1",
            tool_name="public_search",
            arguments_digest="sha256:synthetic",
            expires_at_epoch_ms=2_000,
        )
        self._assert_frozen_slots_dataclass(binding)
        with self.assertRaises(ValueError):
            resolved["ToolRequest"](
                contract_version="tool-request/1",
                tool_name="different_tool",
                arguments=resolved["JsonObject"](),
                timeout_ms=1_000,
                approval_binding=binding,
                idempotency_key="idempotency-1",
                has_side_effects=True,
                max_output_bytes=1_024,
            )
        error = resolved["ToolError"](
            code="tool.timeout",
            category="timeout",
            retryable=True,
            safe_message="tool timed out",
            side_effect_status="none",
        )
        result = resolved["ToolResult"](
            contract_version="tool-result/1",
            output=None,
            error=error,
            output_bytes=0,
            is_truncated=False,
            metadata=resolved["JsonObject"](),
        )
        self._assert_frozen_slots_dataclass(error)
        self._assert_frozen_slots_dataclass(result)

    def test_provider_contract_normalizes_messages_usage_and_errors(self) -> None:
        run_module = importlib.import_module("efficiency_platform_agent.core.run")
        required_types = (
            "JsonObject",
            "ProviderError",
            "ProviderMessage",
            "ProviderRequest",
            "ProviderResult",
            "ProviderUsage",
        )
        resolved = {name: self._require_type(run_module, name) for name in required_types}
        request_fields = {field.name for field in fields(resolved["ProviderRequest"])}
        result_fields = {field.name for field in fields(resolved["ProviderResult"])}

        self.assertTrue(
            {
                "contract_version",
                "messages",
                "options",
                "timeout_ms",
            }.issubset(request_fields)
        )
        self.assertTrue(
            {"contract_version", "message", "usage", "error"}.issubset(
                result_fields
            )
        )
        usage = resolved["ProviderUsage"](
            input_tokens=10,
            output_tokens=5,
            cached_tokens=2,
            reasoning_tokens=1,
            cost_microunits=3,
        )
        self._assert_frozen_slots_dataclass(usage)
        message = resolved["ProviderMessage"](role="user", content="hello")
        with self.assertRaises(TypeError):
            resolved["ProviderRequest"](
                contract_version="provider-request/1",
                messages=[message],
                options=resolved["JsonObject"](),
                timeout_ms=1_000,
            )
        with self.assertRaises(ValueError):
            resolved["ProviderUsage"](
                input_tokens=-1,
                output_tokens=0,
                cached_tokens=0,
                reasoning_tokens=0,
                cost_microunits=0,
            )

    def test_protocols_expose_descriptors_and_structured_requests(self) -> None:
        ports_module = importlib.import_module("efficiency_platform_agent.core.ports")
        run_module = importlib.import_module("efficiency_platform_agent.core.run")
        ExtensionDescriptor = self._require_type(run_module, "ExtensionDescriptor")
        SupervisorTask = self._require_type(run_module, "SupervisorTask")
        ToolRequest = self._require_type(run_module, "ToolRequest")
        ProviderRequest = self._require_type(run_module, "ProviderRequest")

        for name in ("StrategyExecutor", "AgentPlugin", "Tool", "ModelProvider"):
            port = self._require_type(ports_module, name)
            with self.subTest(port=name):
                self.assertIs(port.__annotations__.get("descriptor"), ExtensionDescriptor)

        agent_parameters = tuple(
            inspect.signature(ports_module.AgentPlugin.run).parameters.values()
        )
        tool_parameters = tuple(
            inspect.signature(ports_module.Tool.invoke).parameters.values()
        )
        provider_parameters = tuple(
            inspect.signature(ports_module.ModelProvider.complete).parameters.values()
        )
        self.assertEqual(agent_parameters[1].annotation, SupervisorTask)
        self.assertEqual(len(agent_parameters), 2)
        self.assertEqual(tool_parameters[1].annotation, ToolRequest)
        self.assertEqual(provider_parameters[1].annotation, ProviderRequest)

    def test_run_status_transition_table_covers_recovery_and_terminal_rules(self) -> None:
        run_module = importlib.import_module("efficiency_platform_agent.core.run")
        enums_module = importlib.import_module("efficiency_platform_agent.core.enums")
        RunStatus = enums_module.RunStatus
        transitions = self._require_type(run_module, "RUN_STATUS_TRANSITIONS")
        is_valid = self._require_type(run_module, "is_valid_run_status_transition")
        validate = self._require_type(run_module, "validate_run_status_transition")

        for waiting_status in (
            RunStatus.WAITING_TOOL,
            RunStatus.WAITING_INPUT,
            RunStatus.WAITING_APPROVAL,
        ):
            with self.subTest(waiting=waiting_status):
                self.assertTrue(is_valid(RunStatus.RUNNING, waiting_status))
                self.assertTrue(is_valid(waiting_status, RunStatus.RUNNING))
                self.assertTrue(is_valid(waiting_status, RunStatus.CANCELLED))
                self.assertTrue(is_valid(waiting_status, RunStatus.TIMED_OUT))
                self.assertTrue(is_valid(waiting_status, RunStatus.FAILED))

        for terminal_status in (
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.TIMED_OUT,
        ):
            with self.subTest(terminal=terminal_status):
                self.assertEqual(transitions[terminal_status], frozenset())
                self.assertFalse(is_valid(terminal_status, RunStatus.RUNNING))
                self.assertTrue(is_valid(terminal_status, terminal_status))

        self.assertFalse(is_valid(RunStatus.CREATED, RunStatus.RUNNING))
        self.assertFalse(is_valid(RunStatus.WAITING_TOOL, RunStatus.SUCCEEDED))
        with self.assertRaises(ValueError):
            validate(RunStatus.CREATED, RunStatus.SUCCEEDED)
        with self.assertRaises(TypeError):
            transitions[RunStatus.CREATED] = frozenset()

    def _require_type(self, module: object, name: str):
        self.assertTrue(hasattr(module, name), f"missing contract: {name}")
        return getattr(module, name)

    def _assert_frozen_slots_dataclass(self, value: object) -> None:
        self.assertTrue(is_dataclass(value))
        self.assertTrue(hasattr(type(value), "__slots__"))
        self.assertTrue(type(value).__dataclass_params__.frozen)

    def _budget(self, budget_type):
        return budget_type(
            max_iterations=3,
            max_tool_calls=2,
            max_input_tokens=100,
            max_output_tokens=50,
            timeout_ms=1_000,
            max_cost_microunits=25,
        )


if __name__ == "__main__":
    unittest.main()

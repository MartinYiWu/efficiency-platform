"""上下文治理须安装在真实组合根和付费传输边界。"""

import ast
from pathlib import Path

ROOT = Path(__file__).parents[2] / "src" / "efficiency_platform_agent"


def test_real_factory_installs_controlled_provider():
    source = (ROOT / "harness/local_real_factory.py").read_text(encoding="utf-8")
    assert "ControlledModelProvider(" in source


def test_paid_finalization_occurs_after_reserve_before_network():
    source = (ROOT / "providers/paid_http.py").read_text(encoding="utf-8")
    reserve = source.index("reservation = self.ledger.reserve(")
    send = source.index("response = await self.inner.handle_async_request(request)")
    assert reserve < source.index("await context_guard.before_send(payload)") < send


def test_business_stage_boundaries_are_explicit():
    for path in (
        "agents/conversation/general_agent.py",
        "orchestration/intent_interpreter.py",
        "orchestration/intent_v2/interpreter.py",
        "agents/operation/specialists/model_backed.py",
        "agents/operation/specialists/scenario_model_executor.py",
        "orchestration/research_v2/tool_loop.py",
        "agents/customer_service/model_gateway.py",
        "agents/hr/service.py",
    ):
        assert "@stage_entry(" in (ROOT / path).read_text(encoding="utf-8"), path


def test_actual_provider_construction_is_only_in_registered_composition_root():
    constructors = {"DeepSeekStreamingProvider", "DeepSeekModelProvider"}
    found = []
    for path in ROOT.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in constructors
            ):
                found.append(path.relative_to(ROOT).as_posix())
    assert found == ["harness/local_real_factory.py"]


def test_model_dispatch_calls_only_exist_in_registered_boundaries():
    allowed = {
        "agents/conversation/general_agent.py",
        "agents/customer_service/model_gateway.py",
        "agents/hr/service.py",
        "agents/operation/specialists/model_backed.py",
        "agents/operation/specialists/scenario_model_executor.py",
        "capabilities/model/runtime.py",
        "capabilities/research/v2/model_decisions.py",
        "context/dispatch.py",
        "orchestration/context_gate.py",
        "harness/referenced_content_model.py",
        "harness/hr_factory.py",
        "capabilities/model/memory_derive.py",
        "orchestration/intent_interpreter.py",
        "orchestration/intent_v2/interpreter.py",
        "orchestration/research_v2/tool_loop.py",
    }
    violations = []
    for path in ROOT.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if (
                not isinstance(node, ast.Call)
                or not isinstance(node.func, ast.Attribute)
                or node.func.attr not in {"complete", "stream", "stream_complete"}
            ):
                continue
            receiver = ast.unparse(node.func.value)
            if (
                "model" in receiver.lower()
                or "provider" in receiver.lower()
                or receiver == "selected"
            ):
                relative = path.relative_to(ROOT).as_posix()
                if relative not in allowed:
                    violations.append((relative, node.lineno))
    assert not violations


def test_checkpoint_provider_fence_wraps_each_complete_and_stream_call():
    tree = ast.parse(
        (ROOT / "orchestration/context_gate.py").read_text(encoding="utf-8")
    )
    calls = []
    for method in ast.walk(tree):
        if not isinstance(method, ast.AsyncFunctionDef) or method.name not in {
            "complete",
            "stream",
        }:
            continue
        for node in ast.walk(method):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and ast.unparse(node.func.value) == "self._provider"
            ):
                calls.append(method.name)
                assert any(
                    isinstance(block, ast.AsyncWith)
                    and any(
                        ast.unparse(item.context_expr) == "self._guard()"
                        for item in block.items
                    )
                    and any(descendant is node for descendant in ast.walk(block))
                    for block in ast.walk(method)
                )
    assert sorted(calls) == ["complete", "stream"]


def test_derive_boundary_requires_original_paid_and_context_chain():
    source = (ROOT / "capabilities/model/memory_derive.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    constructors = {
        "AsyncClient",
        "AsyncOpenAI",
        "DeepSeekModelProvider",
        "DeepSeekStreamingProvider",
        "SqlitePaidBudgetLedger",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else ""
            )
            assert name not in constructors | {"authorize"}
    assert 'node_id="memory.derive"' in source
    assert "self.store.consume_attempt(self.lease)" in source
    assert "transport.ledger is not self.store.ledger" in source
    assert "not transport.require_context_guard" in source
    assert "provider.dispatch.stage_store is None" in source
    assert "current_run_control()" in source

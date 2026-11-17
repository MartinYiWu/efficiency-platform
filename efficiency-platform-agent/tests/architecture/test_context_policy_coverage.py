"""冻结入口清单与真实组合根的上下文治理覆盖。"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2] / "src/efficiency_platform_agent"

ENTRYPOINTS = (
    ("agents/conversation/general_agent.py", "execute", "direct"),
    ("orchestration/intent_interpreter.py", "execute", "intent"),
    ("orchestration/intent_v2/interpreter.py", "execute", "intent-plan"),
    ("orchestration/intent_v2/interpreter.py", "execute", "intent-v2"),
    ("agents/operation/specialists/model_backed.py", "run", "operation-specialist"),
    (
        "agents/operation/specialists/scenario_model_executor.py",
        "generate_with_usage",
        "operation-scenario",
    ),
    ("orchestration/research_v2/tool_loop.py", "_plan", "research-plan"),
    ("orchestration/research_v2/tool_loop.py", "_reflect", "research-reflect"),
    ("orchestration/research_v2/tool_loop.py", "_synthesize", "research-synthesize"),
    ("agents/customer_service/model_gateway.py", "complete", "customer-service"),
    ("agents/customer_service/model_gateway.py", "stream_complete", "customer-service"),
    ("agents/hr/service.py", "_generate", "hr"),
)


@pytest.mark.parametrize("path,function,node", ENTRYPOINTS)
def test_registered_business_entrypoint_binds_one_trusted_stage(path, function, node):
    module = ast.parse((ROOT / path).read_text(encoding="utf-8-sig"))
    matches = []
    for value in ast.walk(module):
        if not isinstance(value, ast.AsyncFunctionDef) or value.name != function:
            continue
        decorators = [
            decorator
            for decorator in value.decorator_list
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Name)
            and decorator.func.id == "stage_entry"
        ]
        if decorators:
            assert len(decorators) == 1
            if ast.literal_eval(decorators[0].args[0]) == node:
                matches.append(decorators[0])
    assert len(matches) == 1
    assert ast.literal_eval(matches[0].args[0]) == node
    inputs = next(
        (keyword.value for keyword in matches[0].keywords if keyword.arg == "inputs"),
        None,
    )
    assert inputs is not None and ast.literal_eval(inputs)


def test_production_provider_installation_precedes_registry_and_business_gateways():
    module = ast.parse(
        (ROOT / "harness/local_real_factory.py").read_text(encoding="utf-8")
    )
    nodes = list(ast.walk(module))
    guards = [
        value
        for value in nodes
        if isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id
        in {"ControlledModelProvider", "ControlledStreamingModelProvider"}
    ]
    registrations = [
        value
        for value in nodes
        if isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and value.func.attr == "register"
        and isinstance(value.func.value, ast.Name)
        and value.func.value.id == "provider_registry"
    ]
    assert len(guards) == 2 and len(registrations) == 1
    assert all(value.lineno < registrations[0].lineno for value in guards)

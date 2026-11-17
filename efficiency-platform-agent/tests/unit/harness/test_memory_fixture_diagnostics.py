"""本机集成失败诊断不输出异常正文或运行状态。"""
from types import SimpleNamespace

from tests.integration.context_control.private_memory_http_fixture import (
    SafeFailureRecorder,
    failure_code,
)


def test_failure_diagnostic_whitelists_code_type_and_project_location(capsys):
    SafeFailureRecorder().record(SimpleNamespace(error_code="GRAPH_EXECUTION_FAILED", error_type="ValueError", error_location="runtime.py:123:execute", message="private-body-marker", state={"secret": "private-body-marker"}))
    output = capsys.readouterr().out
    assert "GRAPH_EXECUTION_FAILED" in output and "runtime.py:123:execute" in output
    assert "private-body-marker" not in output
    SafeFailureRecorder().record(SimpleNamespace(error_code="PRIVATE text", error_type="bad type", error_location="D:/private/body"))
    assert capsys.readouterr().out == "D17J_SAFE_FAILURE {}\n"
    assert failure_code({"failure": {"code": "MEMORY_THREAD_FENCED", "safe_message": "private-body-marker"}}) == "MEMORY_THREAD_FENCED"
    assert failure_code({"failure": {"code": "private body"}}) is None

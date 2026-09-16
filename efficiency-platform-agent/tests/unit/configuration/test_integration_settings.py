from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from efficiency_platform_agent.configuration.integration import (
    GateAuthorization,
    IntegrationGate,
    S7IntegrationSettings,
)


def test_gates_default_closed_and_unselected_missing_is_empty():
    with TemporaryDirectory() as folder:
        path = Path(folder) / ".env"
        path.write_text("DEEPSEEK_API_KEY=synthetic-secret\n", encoding="utf-8")
        settings = S7IntegrationSettings.from_env_file(path)
    assert all(value is False for value in settings.gates.values())
    assert settings.for_gate(IntegrationGate.DEEPSEEK_CHAT) == ()


def test_selected_gate_reports_only_its_missing_keys():
    with TemporaryDirectory() as folder:
        path = Path(folder) / ".env"
        path.write_text("S7_GATE_DEEPSEEK_CHAT=true\n", encoding="utf-8")
        settings = S7IntegrationSettings.from_env_file(path)
    assert settings.for_gate(IntegrationGate.DEEPSEEK_CHAT) == (
        "AGENT_LLM_DEEPSEEK_BASE_URL",
        "AGENT_LLM_DEEPSEEK_API_KEY",
        "AGENT_LLM_DEEPSEEK_FAST_MODEL",
        "AGENT_LLM_DEEPSEEK_BALANCED_MODEL",
        "AGENT_LLM_DEEPSEEK_STRONG_MODEL",
    )


def test_explicit_env_file_cannot_be_overridden_by_process_environment(monkeypatch):
    monkeypatch.setenv("AGENT_LLM_DEEPSEEK_API_KEY", "process-secret")
    with TemporaryDirectory() as folder:
        path = Path(folder) / ".env"
        path.write_text(
            "S7_GATE_DEEPSEEK_CHAT=true\n"
            "AGENT_LLM_DEEPSEEK_BASE_URL=https://example.invalid\n",
            encoding="utf-8",
        )
        settings = S7IntegrationSettings.from_env_file(path)
    assert "AGENT_LLM_DEEPSEEK_API_KEY" in settings.for_gate(
        IntegrationGate.DEEPSEEK_CHAT
    )


def test_secret_value_is_not_exposed_by_settings_rendering():
    secret = "synthetic-secret-value"
    settings = S7IntegrationSettings(deepseek_api_key=secret)
    rendered = " ".join(
        (str(settings), repr(settings), str(settings.model_dump()), repr(settings))
    )
    assert secret not in rendered


def _probe_authorization(**overrides):
    values = {
        "approval_id": "approval-synthetic",
        "run_stamp": "run-synthetic",
        "gate": IntegrationGate.DEEPSEEK_CHAT,
        "action": "network_probe",
        "approved_by": "reviewer",
        "executor_id": "executor",
        "target_digest": "target-digest",
        "input_digest": "input-digest",
        "approved_at_epoch_ms": 1_000,
        "expires_at_epoch_ms": 2_000,
        "max_network_calls": 1,
        "max_model_calls": 1,
        "max_search_calls": 0,
        "max_cost_microunits": 0,
        "max_database_rows_read": 0,
        "max_database_rows_written": 0,
        "max_redis_records": 0,
        "max_cos_objects": 0,
        "max_bytes": 1024,
        "cleanup_owner": "owner",
        "cleanup_deadline_epoch_ms": 2_000,
        "cleanup_procedure_id": "cleanup-synthetic",
    }
    values.update(overrides)
    return GateAuthorization(**values)


def test_network_probe_rejects_write_or_charge_limits():
    with pytest.raises(ValueError, match="不得写入或计费"):
        GateAuthorization(**_probe_authorization(max_redis_records=1).model_dump())


def test_authorization_rejects_cleanup_deadline_before_expiry():
    with pytest.raises(ValueError, match="清理截止时间"):
        _probe_authorization(cleanup_deadline_epoch_ms=1_999)


def test_authorization_matches_request_context_and_action():
    authorization = _probe_authorization()
    authorization.validate_request(
        run_stamp="run-synthetic",
        executor_id="executor",
        gate=IntegrationGate.DEEPSEEK_CHAT,
        action="network_probe",
        target_digest="target-digest",
        input_digest="input-digest",
        model_ids=(),
        resource_ids=(),
        now_epoch_ms=1_500,
        required_limits={"max_network_calls": 1, "max_cost_microunits": 0},
        cleanup_owner="owner",
        cleanup_procedure_id="cleanup-synthetic",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("run_stamp", "another-run"),
        ("executor_id", "another-executor"),
        ("target_digest", "another-target"),
        ("input_digest", "another-input"),
        ("model_ids", ("deepseek-pro",)),
        ("resource_ids", ("resource-other",)),
        ("action", "write_acceptance"),
        ("gate", IntegrationGate.COS_ARTIFACT),
        ("cleanup_owner", "another-owner"),
        ("cleanup_procedure_id", "another-cleanup"),
    ],
)
def test_authorization_rejects_request_context_mismatch(field, value):
    authorization = _probe_authorization()
    request = {
        "run_stamp": "run-synthetic",
        "executor_id": "executor",
        "gate": IntegrationGate.DEEPSEEK_CHAT,
        "action": "network_probe",
        "target_digest": "target-digest",
        "input_digest": "input-digest",
        "model_ids": (),
        "resource_ids": (),
        "now_epoch_ms": 1_500,
        "required_limits": {"max_network_calls": 1},
        "cleanup_owner": "owner",
        "cleanup_procedure_id": "cleanup-synthetic",
    }
    request[field] = value
    with pytest.raises(ValueError, match="授权上下文不匹配"):
        authorization.validate_request(**request)


def test_authorization_rejects_expired_or_excessive_requested_limits():
    authorization = _probe_authorization()
    with pytest.raises(ValueError, match="授权已过期"):
        authorization.validate_request(
            run_stamp="run-synthetic",
            executor_id="executor",
            gate=IntegrationGate.DEEPSEEK_CHAT,
            action="network_probe",
            target_digest="target-digest",
            input_digest="input-digest",
            now_epoch_ms=2_000,
            required_limits={},
            cleanup_owner="owner",
            cleanup_procedure_id="cleanup-synthetic",
        )
    with pytest.raises(ValueError, match="授权子上限不足"):
        authorization.validate_request(
            run_stamp="run-synthetic",
            executor_id="executor",
            gate=IntegrationGate.DEEPSEEK_CHAT,
            action="network_probe",
            target_digest="target-digest",
            input_digest="input-digest",
            now_epoch_ms=1_500,
            required_limits={"max_network_calls": 2},
            cleanup_owner="owner",
            cleanup_procedure_id="cleanup-synthetic",
        )


def test_document_and_end_to_end_gates_delay_configuration_validation():
    settings = S7IntegrationSettings(
        gates={
            IntegrationGate.DOCUMENT_PIPELINE.value: True,
            IntegrationGate.END_TO_END.value: False,
        }
    )
    assert settings.for_gate(IntegrationGate.DOCUMENT_PIPELINE) == (
        "AGENT_COS_SECRET_ID",
        "AGENT_COS_SECRET_KEY",
        "AGENT_COS_REGION",
        "AGENT_COS_BUCKET",
        "AGENT_COS_BASE_URL",
    )
    settings = S7IntegrationSettings(gates={IntegrationGate.END_TO_END.value: True})
    assert "AGENT_COS_BASE_URL" in settings.for_gate(IntegrationGate.END_TO_END)

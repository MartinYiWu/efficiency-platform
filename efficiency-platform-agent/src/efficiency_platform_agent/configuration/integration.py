"""默认关闭的 S7 Gate 配置和动作级授权。"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class IntegrationGate(StrEnum):
    DEEPSEEK_CHAT = "deepseek_chat"
    DEEPSEEK_WEB_SEARCH = "deepseek_web_search"
    POSTGRES_PGVECTOR = "postgres_pgvector"
    REDIS_TASKIQ = "redis_taskiq"
    COS_ARTIFACT = "cos_artifact"
    DOCUMENT_PIPELINE = "document_pipeline"
    END_TO_END = "end_to_end"


class GateAction(StrEnum):
    NETWORK_PROBE = "network_probe"
    READ_ACCEPTANCE = "read_acceptance"
    WRITE_ACCEPTANCE = "write_acceptance"
    CHARGED_ACCEPTANCE = "charged_acceptance"


class GateAuthorization(BaseModel):
    """绑定批准人、执行者、资源摘要、子上限和清理责任。"""

    model_config = ConfigDict(extra="forbid", frozen=True)
    approval_id: str
    run_stamp: str
    gate: IntegrationGate
    action: GateAction
    approved_by: str
    executor_id: str
    target_digest: str
    input_digest: str
    model_ids: tuple[str, ...] = ()
    resource_ids: tuple[str, ...] = ()
    approved_at_epoch_ms: int = Field(gt=0)
    expires_at_epoch_ms: int = Field(gt=0)
    max_network_calls: int = Field(ge=0)
    max_model_calls: int = Field(ge=0)
    max_search_calls: int = Field(ge=0)
    max_cost_microunits: int = Field(ge=0)
    max_database_rows_read: int = Field(ge=0)
    max_database_rows_written: int = Field(ge=0)
    max_redis_records: int = Field(ge=0)
    max_cos_objects: int = Field(ge=0)
    max_bytes: int = Field(ge=0)
    cleanup_owner: str
    cleanup_deadline_epoch_ms: int = Field(gt=0)
    cleanup_procedure_id: str

    @model_validator(mode="after")
    def validate_binding(self):
        """校验有效期、清理责任和探测动作的零写入零计费约束。"""
        if self.expires_at_epoch_ms <= self.approved_at_epoch_ms:
            raise ValueError("授权有效期必须晚于批准时间")
        if self.cleanup_deadline_epoch_ms < self.expires_at_epoch_ms:
            raise ValueError("清理截止时间不能早于授权截止时间")
        if self.action is GateAction.NETWORK_PROBE and (
            self.max_cost_microunits
            or self.max_database_rows_written
            or self.max_redis_records
            or self.max_cos_objects
        ):
            raise ValueError("NETWORK_PROBE不得写入或计费")
        return self

    def validate_request(
        self,
        *,
        run_stamp: str,
        executor_id: str,
        gate: IntegrationGate | str,
        action: GateAction | str,
        target_digest: str,
        input_digest: str,
        model_ids: tuple[str, ...] = (),
        resource_ids: tuple[str, ...] = (),
        now_epoch_ms: int,
        required_limits: Mapping[str, int],
        cleanup_owner: str,
        cleanup_procedure_id: str,
    ) -> None:
        """校验一次即将执行的动作是否完全落在本次授权范围内。"""
        try:
            requested_gate = IntegrationGate(gate)
            requested_action = GateAction(action)
        except (TypeError, ValueError) as error:
            raise ValueError("授权上下文不匹配") from error
        if (
            run_stamp != self.run_stamp
            or executor_id != self.executor_id
            or requested_gate is not self.gate
            or requested_action is not self.action
            or target_digest != self.target_digest
            or input_digest != self.input_digest
            or model_ids != self.model_ids
            or resource_ids != self.resource_ids
            or cleanup_owner != self.cleanup_owner
            or cleanup_procedure_id != self.cleanup_procedure_id
        ):
            raise ValueError("授权上下文不匹配")
        if not isinstance(now_epoch_ms, int) or isinstance(now_epoch_ms, bool):
            raise TypeError("授权时间无效")
        if now_epoch_ms >= self.expires_at_epoch_ms:
            raise ValueError("授权已过期")
        if now_epoch_ms < self.approved_at_epoch_ms:
            raise ValueError("授权尚未生效")
        limits = {
            "max_network_calls": self.max_network_calls,
            "max_model_calls": self.max_model_calls,
            "max_search_calls": self.max_search_calls,
            "max_cost_microunits": self.max_cost_microunits,
            "max_database_rows_read": self.max_database_rows_read,
            "max_database_rows_written": self.max_database_rows_written,
            "max_redis_records": self.max_redis_records,
            "max_cos_objects": self.max_cos_objects,
            "max_bytes": self.max_bytes,
        }
        for name, requested in required_limits.items():
            if (
                name not in limits
                or not isinstance(requested, int)
                or isinstance(requested, bool)
            ):
                raise ValueError("授权子上限不足")
            if requested < 0 or requested > limits[name]:
                raise ValueError("授权子上限不足")
        if requested_action is GateAction.NETWORK_PROBE and any(
            required_limits.get(name, 0) > 0
            for name in (
                "max_cost_microunits",
                "max_database_rows_written",
                "max_redis_records",
                "max_cos_objects",
            )
        ):
            raise ValueError("探测动作不得写入或计费")


class S7IntegrationSettings(BaseModel):
    """仅从显式 env 文件读取的敏感配置，默认不启用任何 Gate。"""

    model_config = ConfigDict(extra="ignore", frozen=True)
    runtime_database_url: SecretStr | None = None
    vector_database_url: SecretStr | None = None
    task_broker_url: SecretStr | None = None
    run_event_redis_url: SecretStr | None = None
    deepseek_base_url: SecretStr | None = None
    deepseek_api_key: SecretStr | None = None
    deepseek_fast_model: SecretStr | None = None
    deepseek_balanced_model: SecretStr | None = None
    deepseek_strong_model: SecretStr | None = None
    cos_secret_id: SecretStr | None = None
    cos_secret_key: SecretStr | None = None
    cos_region: SecretStr | None = None
    cos_bucket: SecretStr | None = None
    cos_base_url: SecretStr | None = None
    gates: dict[str, bool] = Field(
        default_factory=lambda: {g.value: False for g in IntegrationGate}
    )
    _KEYS = {
        IntegrationGate.DEEPSEEK_CHAT: (
            "deepseek_base_url",
            "deepseek_api_key",
            "deepseek_fast_model",
            "deepseek_balanced_model",
            "deepseek_strong_model",
        ),
        IntegrationGate.DEEPSEEK_WEB_SEARCH: (
            "deepseek_base_url",
            "deepseek_api_key",
            "deepseek_fast_model",
            "deepseek_balanced_model",
            "deepseek_strong_model",
        ),
        IntegrationGate.POSTGRES_PGVECTOR: (
            "runtime_database_url",
            "vector_database_url",
        ),
        IntegrationGate.REDIS_TASKIQ: ("task_broker_url", "run_event_redis_url"),
        IntegrationGate.COS_ARTIFACT: (
            "cos_secret_id",
            "cos_secret_key",
            "cos_region",
            "cos_bucket",
            "cos_base_url",
        ),
        IntegrationGate.DOCUMENT_PIPELINE: (
            "cos_secret_id",
            "cos_secret_key",
            "cos_region",
            "cos_bucket",
            "cos_base_url",
        ),
        IntegrationGate.END_TO_END: (
            "runtime_database_url",
            "vector_database_url",
            "task_broker_url",
            "run_event_redis_url",
            "deepseek_base_url",
            "deepseek_api_key",
            "deepseek_fast_model",
            "deepseek_balanced_model",
            "deepseek_strong_model",
            "cos_secret_id",
            "cos_secret_key",
            "cos_region",
            "cos_bucket",
            "cos_base_url",
        ),
    }

    @classmethod
    def from_env_file(cls, path: str | Path) -> S7IntegrationSettings:
        """只读取指定文件，不读取进程环境变量。"""
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(p)
        vals = {}
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                vals[k.strip().lower().removeprefix("agent_")] = (
                    v.strip().strip('"').strip("'")
                )
        normalized = {}
        for k, v in vals.items():
            if k.startswith("llm_deepseek_"):
                k = k.removeprefix("llm_")
            normalized[k] = v
        fields = {
            k: normalized.get(k.upper(), normalized.get(k))
            for k in cls.model_fields
            if k != "gates"
            and (normalized.get(k.upper(), normalized.get(k)) is not None)
        }
        gates = {
            g.value: normalized.get(f"s7_gate_{g.name.lower()}", "false").lower()
            == "true"
            for g in IntegrationGate
        }
        return cls(**cast(dict[str, Any], fields), gates=gates)

    def for_gate(self, gate: IntegrationGate | str) -> tuple[str, ...]:
        """仅报告选中 Gate 的缺失键。"""
        g = IntegrationGate(gate)
        if not self.gates.get(g.value, False):
            return ()
        labels = {
            "deepseek_base_url": "AGENT_LLM_DEEPSEEK_BASE_URL",
            "deepseek_api_key": "AGENT_LLM_DEEPSEEK_API_KEY",
            "deepseek_fast_model": "AGENT_LLM_DEEPSEEK_FAST_MODEL",
            "deepseek_balanced_model": "AGENT_LLM_DEEPSEEK_BALANCED_MODEL",
            "deepseek_strong_model": "AGENT_LLM_DEEPSEEK_STRONG_MODEL",
            "runtime_database_url": "AGENT_RUNTIME_DATABASE_URL",
            "vector_database_url": "AGENT_VECTOR_DATABASE_URL",
            "task_broker_url": "AGENT_TASK_BROKER_URL",
            "run_event_redis_url": "AGENT_RUN_EVENT_REDIS_URL",
            "cos_secret_id": "AGENT_COS_SECRET_ID",
            "cos_secret_key": "AGENT_COS_SECRET_KEY",
            "cos_region": "AGENT_COS_REGION",
            "cos_bucket": "AGENT_COS_BUCKET",
            "cos_base_url": "AGENT_COS_BASE_URL",
        }
        return tuple(
            labels[k] for k in self._KEYS.get(g, ()) if getattr(self, k) is None
        )


__all__ = [
    "GateAction",
    "GateAuthorization",
    "IntegrationGate",
    "S7IntegrationSettings",
]

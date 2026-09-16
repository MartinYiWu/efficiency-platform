"""运营 Supervisor 等待输入与恢复契约。"""

from __future__ import annotations

from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from efficiency_platform_agent.core.run import JsonObject, JsonValue
from efficiency_platform_agent.orchestration.contracts import CheckpointView


class OperationResumeValueV1(BaseModel):
    """绑定请求和计划修订版本的恢复值。"""

    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_version: Literal["operation-resume/1"] = "operation-resume/1"
    request_id: str
    plan_revision: int = Field(ge=0)
    supplemental: dict[str, object] = Field(default_factory=dict)
    fence_token: int = Field(default=0, ge=0)

    def to_json(self) -> JsonObject:
        return JsonObject(
            (
                ("contract_version", self.contract_version),
                ("request_id", self.request_id),
                ("plan_revision", self.plan_revision),
                (
                    "supplemental",
                    JsonObject(
                        tuple(
                            (str(key), cast(JsonValue, value))
                            for key, value in self.supplemental.items()
                        )
                    ),
                ),
                ("fence_token", self.fence_token),
            )
        )


class OperationResumeValidator:
    """校验恢复值与检查点绑定的请求标识、计划修订和栅栏令牌。"""

    def validate(self, checkpoint: CheckpointView, resume_value: JsonObject) -> None:
        if not isinstance(resume_value, JsonObject):
            raise ValueError("RESUME_VALUE_INVALID")  # noqa: TRY004 - 保持稳定错误码
        raw = dict(resume_value.items)
        required = {
            "contract_version",
            "request_id",
            "plan_revision",
            "supplemental",
            "fence_token",
        }
        if set(raw) != required:
            raise ValueError("RESUME_VALUE_INVALID")
        if raw["contract_version"] != "operation-resume/1":
            raise ValueError("RESUME_VALUE_INVALID")
        if (
            not isinstance(raw["request_id"], str)
            or not raw["request_id"].strip()
            or not isinstance(raw["plan_revision"], int)
            or isinstance(raw["plan_revision"], bool)
            or raw["plan_revision"] < 0
            or not isinstance(raw["fence_token"], int)
            or isinstance(raw["fence_token"], bool)
            or raw["fence_token"] < 0
            or not isinstance(raw["supplemental"], JsonObject)
        ):
            raise ValueError("RESUME_VALUE_INVALID")
        binding = dict(checkpoint.resume_binding.items)
        for key in ("request_id", "plan_revision", "fence_token"):
            if key in binding and raw.get(key) != binding[key]:
                raise ValueError("STALE_RESUME_INPUT")


__all__ = ["OperationResumeValidator", "OperationResumeValueV1"]

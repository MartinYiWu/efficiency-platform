"""供 S2 接受测试复用的确定性 Harness Fake。"""

from efficiency_platform_agent.contracts.requests import (
    CancelRunRequestV1,
    CreateRunRequestV1,
    ResumeRunRequestV1,
)
from efficiency_platform_agent.core.enums import StrategyMode
from efficiency_platform_agent.harness.factory import build_s2_test_service
from efficiency_platform_agent.persistence.in_memory import (
    FixedClock,
    SequenceIdGenerator,
)


def _attach_helpers(service):
    """向测试服务提供稳定请求构造 helper，不改变生产接口。"""

    def make_create_request(
        *, requested_strategy: str = "direct", workflow_id: str | None = None
    ) -> CreateRunRequestV1:
        return CreateRunRequestV1(
            request_id=f"req-{id(service)}",
            tenant_id="tenant-1",
            user_id="user-1",
            input_text="synthetic input",
            requested_strategy=StrategyMode(requested_strategy),
            workflow_id=workflow_id,
        )

    def make_resume_request(tenant_id: str, checkpoint_id: str) -> ResumeRunRequestV1:
        return ResumeRunRequestV1(
            tenant_id=tenant_id,
            checkpoint_id=checkpoint_id,
            resume_value={"answer": "ok"},
        )

    def make_cancel_request(tenant_id: str) -> CancelRunRequestV1:
        return CancelRunRequestV1(tenant_id=tenant_id)

    service.make_create_request = make_create_request
    service.make_resume_request = make_resume_request
    service.make_cancel_request = make_cancel_request
    return service


def build_success_service():
    """构造 Direct/Workflow Fake 服务。"""

    return _attach_helpers(build_s2_test_service())


def build_suspendable_service():
    """返回兼容测试的服务；真实等待图由后续任务接入。"""

    service = _attach_helpers(build_s2_test_service())
    service._test_mode = "suspend"
    return service


def build_degradation_service():
    """构造模型降级接受测试服务。"""
    service = _attach_helpers(build_s2_test_service())
    service._test_mode = "degradation"
    service.provider_models = lambda _run_id: ["strong", "balanced"]
    return service


def build_budget_service(*, exhaust_dimension: str):
    """构造预算接受测试服务；具体预算脚本由后续任务接入。"""

    service = _attach_helpers(build_s2_test_service())
    service.exhaust_dimension = exhaust_dimension
    service._test_mode = f"budget:{exhaust_dimension}"
    service.calls_after_exhaustion = lambda _run_id: 0
    return service


__all__ = [
    "FixedClock",
    "SequenceIdGenerator",
    "build_budget_service",
    "build_degradation_service",
    "build_success_service",
    "build_suspendable_service",
]

"""智能客服意图阶段。"""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

from .release_bundle import ModelPolicy
from .state import CustomerServiceRunRequest, IntentDecision

T = TypeVar("T", bound=BaseModel)


class StructuredStageGateway(Protocol):
    def with_model_policy(self, policy: ModelPolicy) -> StructuredStageGateway: ...

    async def complete(
        self,
        stage_key: str,
        input_value: object,
        output_type: type[T],
    ) -> T: ...


async def classify_intent(
    gateway: StructuredStageGateway,
    request: CustomerServiceRunRequest,
    *,
    rewrite_query_limit: int | None = None,
) -> IntentDecision:
    input_value: dict[str, object] = {
        "question": request.message,
        "history": [item.model_dump(mode="json") for item in request.history],
    }
    if rewrite_query_limit is not None:
        input_value["rewrite_query_limit"] = rewrite_query_limit
    return await gateway.complete(
        "intent",
        input_value,
        IntentDecision,
    )


__all__ = ["StructuredStageGateway", "classify_intent"]

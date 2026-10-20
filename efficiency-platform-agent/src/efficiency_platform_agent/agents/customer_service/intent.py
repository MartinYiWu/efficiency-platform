"""智能客服意图阶段。"""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

from .state import CustomerServiceRunRequest, IntentDecision

T = TypeVar("T", bound=BaseModel)


class StructuredStageGateway(Protocol):
    async def complete(
        self,
        stage_key: str,
        input_value: object,
        output_type: type[T],
    ) -> T: ...


async def classify_intent(
    gateway: StructuredStageGateway, request: CustomerServiceRunRequest
) -> IntentDecision:
    return await gateway.complete(
        "intent",
        {
            "question": request.message,
            "history": [item.model_dump(mode="json") for item in request.history],
        },
        IntentDecision,
    )


__all__ = ["StructuredStageGateway", "classify_intent"]

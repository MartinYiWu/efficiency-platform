"""研究执行预算、来源配额和调用账本的边界契约。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from efficiency_platform_agent.core.budget_lease import (
    BudgetCharge,
    BudgetLeasePort,
    BudgetScope,
)


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BudgetScopeV2(_FrozenContract):
    schema_version: Literal["budget-scope/2"] = "budget-scope/2"
    tenant_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    stage: str = Field(min_length=1, max_length=128)
    quota_dimension: str = Field(min_length=1, max_length=128)
    source_account_id: str | None = Field(default=None, min_length=1, max_length=128)

    def to_core(self) -> BudgetScope:
        return BudgetScope(
            tenant_id=self.tenant_id,
            run_id=self.run_id,
            stage=self.stage,
            quota_dimension=self.quota_dimension,
            source_account_id=self.source_account_id,
        )


class BudgetChargeV2(_FrozenContract):
    schema_version: Literal["budget-charge/2"] = "budget-charge/2"
    calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    bytes: int = Field(default=0, ge=0)
    cost_microunits: int = Field(default=0, ge=0)
    unknown: bool = False

    def to_core(self) -> BudgetCharge:
        return BudgetCharge(
            calls=self.calls,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            bytes=self.bytes,
            cost_microunits=self.cost_microunits,
            unknown=self.unknown,
        )


class ReservationV2(_FrozenContract):
    schema_version: Literal["budget-reservation/2"] = "budget-reservation/2"
    reservation_id: str = Field(min_length=1, max_length=128)
    invocation_id: str = Field(min_length=1, max_length=128)
    scope: BudgetScopeV2
    charge: BudgetChargeV2
    version: int = Field(ge=0)
    status: Literal["reserved", "dispatched", "settled", "released"] = "reserved"


class LedgerSnapshotV2(_FrozenContract):
    schema_version: Literal["budget-ledger/2"] = "budget-ledger/2"
    scope: BudgetScopeV2
    version: int = Field(ge=0)
    used: BudgetChargeV2
    reserved: BudgetChargeV2
    max_calls: int = Field(ge=0)
    max_bytes: int = Field(ge=0)
    max_cost_microunits: int = Field(ge=0)
    max_input_tokens: int = Field(ge=0)
    max_output_tokens: int = Field(ge=0)
    deadline_epoch_ms: int | None = Field(default=None, ge=0)
    output_token_reserve: int = Field(default=0, ge=0)
    output_time_reserve_ms: int = Field(default=0, ge=0)
    settlement_late: bool = False
    delivery_allowed: bool = True
    over_limit: bool = False

    @model_validator(mode="after")
    def validate_delivery(self) -> LedgerSnapshotV2:
        if self.settlement_late and self.delivery_allowed:
            raise ValueError("LATE_SETTLEMENT_CANNOT_BE_DELIVERED")
        if self.over_limit and self.delivery_allowed:
            raise ValueError("OVER_LIMIT_SETTLEMENT_CANNOT_BE_DELIVERED")
        return self


class BudgetOutcomeV2(_FrozenContract):
    outcome: Literal["success", "failed", "cancelled", "unknown"]
    estimated: bool = False
    dispatch_confirmed: bool = False

    @model_validator(mode="after")
    def validate_unknown(self) -> BudgetOutcomeV2:
        if self.outcome == "unknown" and not self.estimated:
            raise ValueError("UNKNOWN_OUTCOME_MUST_BE_ESTIMATED")
        return self


__all__ = [
    "BudgetChargeV2",
    "BudgetLeasePort",
    "BudgetOutcomeV2",
    "BudgetScopeV2",
    "LedgerSnapshotV2",
    "ReservationV2",
]

"""运营领域的稳定错误契约。"""

from dataclasses import dataclass
from enum import StrEnum


class OperationErrorCode(StrEnum):
    """可供上层稳定处理的运营输入错误。"""

    OPERATION_INPUT_INCOMPLETE = "OPERATION_INPUT_INCOMPLETE"
    OPERATION_IDENTITY_MISMATCH = "OPERATION_IDENTITY_MISMATCH"
    OPERATION_CONTRACT_INVALID = "OPERATION_CONTRACT_INVALID"


@dataclass(frozen=True, slots=True)
class OperationErrorDetail:
    """不包含用户正文的结构化领域错误。"""

    code: OperationErrorCode
    message: str
    missing_condition_ids: tuple[str, ...] = ()


class OperationDomainError(ValueError):
    """运营领域契约校验失败。"""

    def __init__(self, detail: OperationErrorDetail) -> None:
        self.detail = detail
        super().__init__(detail.message)


__all__ = ["OperationDomainError", "OperationErrorCode", "OperationErrorDetail"]

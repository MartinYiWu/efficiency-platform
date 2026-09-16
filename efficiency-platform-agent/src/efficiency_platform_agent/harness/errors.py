"""Harness 边界使用的稳定安全错误。"""

from __future__ import annotations


class HarnessError(ValueError):
    """只向调用方暴露错误码、分类和安全消息。"""

    def __init__(
        self,
        code: str,
        safe_message: str,
        *,
        category: str = "runtime",
        retryable: bool = False,
    ) -> None:
        self.code = code
        self.category = category
        self.retryable = retryable
        self.safe_message = safe_message
        super().__init__(safe_message)


def normalize_error(
    error: BaseException, default_code: str = "INTERNAL_RUNTIME_ERROR"
) -> HarnessError:
    """把内部异常归一化，绝不把异常正文带出 Harness。"""

    if isinstance(error, HarnessError):
        return error
    code = getattr(error, "code", default_code)
    if not isinstance(code, str) or not code.strip():
        code = default_code
    return HarnessError(code, "运行请求处理失败")


__all__ = ["HarnessError", "normalize_error"]

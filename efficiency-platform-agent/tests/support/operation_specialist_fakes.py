"""S5 Specialist 离线 Fake，不读取环境和外部系统。"""

from __future__ import annotations

from collections.abc import Iterable


class ScriptedOperationModel:
    """按预置结果顺序返回模型结果并记录调用次数。"""

    def __init__(self, results: Iterable[object]) -> None:
        self._results = iter(results)
        self.calls: tuple[object, ...] = ()

    async def run(self, value: object) -> object:
        self.calls = (*self.calls, value)
        try:
            return next(self._results)
        except StopIteration as error:
            raise RuntimeError("Fake 模型脚本耗尽") from error


__all__ = ["ScriptedOperationModel"]

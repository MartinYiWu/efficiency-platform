"""发布容量目录；只接受显式登记，模型名称不推导窗口或费用许可。"""

from __future__ import annotations

from efficiency_platform_agent.core.context_control import ModelCapacity


class ModelCapacityUnavailable(ValueError):
    """配置缺失时阻断，不打印未知模型或用户输入。"""

    code = "CONTEXT_CAPACITY_UNVERIFIED"

    def __init__(self) -> None:
        super().__init__("模型容量尚未发布或核实，未发送请求")


class ModelCapacityRegistry:
    """按provider/model/version匹配已核实的不可变容量元数据。"""

    def __init__(self) -> None:
        self._models: dict[tuple[str, str, str], ModelCapacity] = {}

    def register(self, capacity: ModelCapacity) -> None:
        if (
            not isinstance(capacity, ModelCapacity)
            or not capacity.verified
            or capacity.context_window_tokens <= 0
            or capacity.max_output_tokens <= 0
            or capacity.max_input_tokens == 0
        ):
            raise ModelCapacityUnavailable()
        key = capacity.provider, capacity.model, capacity.model_version
        if key in self._models:
            raise ModelCapacityUnavailable()
        self._models[key] = capacity

    def resolve(self, provider: str, model: str, version: str) -> ModelCapacity:
        try:
            return self._models[(provider, model, version)]
        except (KeyError, TypeError):
            raise ModelCapacityUnavailable() from None

"""Prompt Bundle 的显式注册表。"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from .contracts import PromptBundleSpec


class PromptRegistry:
    """仅允许调用方显式登记 Prompt，不执行动态扫描或导入。"""

    def __init__(self) -> None:
        self._specs: dict[str, PromptBundleSpec] = {}

    def register(self, spec: PromptBundleSpec) -> None:
        """登记唯一 Prompt ID。"""
        if not isinstance(spec, PromptBundleSpec):
            raise TypeError("spec 必须为 PromptBundleSpec")
        if spec.prompt_id in self._specs:
            raise ValueError(f"重复 Prompt ID: {spec.prompt_id}")
        self._specs[spec.prompt_id] = spec

    def get(self, prompt_id: str) -> PromptBundleSpec:
        """获取已登记 Prompt，未登记时失败关闭。"""
        try:
            return self._specs[prompt_id]
        except KeyError as exc:
            raise KeyError(f"未注册 Prompt: {prompt_id}") from exc

    def snapshot(self) -> Mapping[str, PromptBundleSpec]:
        """返回不可变登记快照。"""
        return MappingProxyType(dict(self._specs))

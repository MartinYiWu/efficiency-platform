"""显式版本化运营场景包 Registry。"""

from __future__ import annotations

from typing import cast

from efficiency_platform_agent.agents.operation.contracts.scenarios import (
    ScenarioPackManifest,
    validate_scenario_pack,
)


class InMemoryScenarioPackRegistry:
    """只保存经 S3 校验的 Manifest，不负责执行或调度。"""

    def __init__(self, manifests: tuple[ScenarioPackManifest, ...] = ()) -> None:
        self._manifests: dict[tuple[str, str], ScenarioPackManifest] = {}
        for manifest in manifests:
            self.register(manifest)

    def register(self, manifest: ScenarioPackManifest) -> None:
        """显式注册一个场景版本，拒绝重复键。"""

        if not isinstance(manifest, ScenarioPackManifest):
            raise TypeError("manifest必须是ScenarioPackManifest")
        validate_scenario_pack(manifest)
        key = (manifest.scenario_id, manifest.semantic_version)
        if key in self._manifests:
            raise ValueError("场景版本已注册")
        self._manifests[key] = manifest

    def get(self, scenario_id: str, semantic_version: str) -> ScenarioPackManifest:
        """按场景标识和语义版本精确读取 Manifest。"""

        try:
            return self._manifests[(scenario_id, semantic_version)]
        except KeyError as error:
            raise KeyError(f"未知场景版本: {scenario_id}/{semantic_version}") from error

    def list(self) -> tuple[ScenarioPackManifest, ...]:
        """按场景标识和主次修订版本稳定列出 Manifest。"""

        def version_key(item: ScenarioPackManifest) -> tuple[str, tuple[int, int, int]]:
            parts = tuple(int(part) for part in item.semantic_version.split(".")[:3])
            normalized = cast(tuple[int, int, int], (parts + (0, 0, 0))[:3])
            return item.scenario_id, normalized

        return tuple(sorted(self._manifests.values(), key=version_key))


__all__ = ["InMemoryScenarioPackRegistry"]

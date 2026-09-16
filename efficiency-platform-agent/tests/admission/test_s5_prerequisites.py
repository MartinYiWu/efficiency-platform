"""S5 前置契约和范围准入测试。"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import get_type_hints


def test_s5_requires_delivered_s2_s3_s4_contracts() -> None:
    required = (
        ("efficiency_platform_agent.prompts.runtime", "PromptRuntime"),
        (
            "efficiency_platform_agent.agents.operation.contracts.task",
            "OperationTaskSpec",
        ),
        (
            "efficiency_platform_agent.agents.operation.supervisor.dispatch",
            "SpecialistResultEnvelope",
        ),
    )
    for module_name, symbol_name in required:
        module = importlib.import_module(module_name)
        assert hasattr(module, symbol_name), (
            f"缺少前置符号：{module_name}.{symbol_name}"
        )


def test_s4_versioned_envelope_has_typed_full_evidence_field() -> None:
    from efficiency_platform_agent.agents.operation.contracts.evidence import (
        EvidencePack,
    )
    from efficiency_platform_agent.agents.operation.supervisor.dispatch import (
        SpecialistResultEnvelope,
    )

    envelope_fields = get_type_hints(SpecialistResultEnvelope)
    assert envelope_fields["evidence_pack"] == EvidencePack | None
    assert "operation-specialist-result/1" in str(
        SpecialistResultEnvelope.__post_init__.__code__.co_consts
    )


def test_s5_production_code_forbids_external_and_write_dependencies() -> None:
    root = Path("src/efficiency_platform_agent/agents/operation")
    forbidden = {"httpx", "openai", "polars", "fastexcel", "sqlalchemy", "redis"}
    hits: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for name in forbidden:
            if f"import {name}" in text or f"from {name}" in text:
                hits.append(f"{path}:{name}")
    assert hits == [], "S5 运营源码包含禁止依赖：" + ", ".join(hits)

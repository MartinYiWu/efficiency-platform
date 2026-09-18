"""本地来源目录的显式组合入口，保持配置层仅依赖中立契约。"""

from datetime import datetime

from efficiency_platform_agent.capabilities.research.v2.source_admission import (
    SourceAdmission,
)
from efficiency_platform_agent.capabilities.research.v2.sources import (
    VerifiedSourceRegistry,
)
from efficiency_platform_agent.configuration.research_local_sources import (
    validate_local_source_descriptors,
)
from efficiency_platform_agent.contracts.research_sources_v2 import SourceDescriptorV2


def build_local_source_registry(
    descriptors: tuple[SourceDescriptorV2, ...], *, now: datetime
) -> VerifiedSourceRegistry:
    """检查启用来源的当期证据，并复用每次调用重新检查的来源目录。"""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("SOURCE_ADMISSION_NOW_NAIVE")
    validated = validate_local_source_descriptors(descriptors)
    admission = SourceAdmission()
    for descriptor in validated:
        if not descriptor.enabled:
            continue
        decision = admission.evaluate(descriptor, descriptor.admission, now)
        if not decision.allowed:
            raise ValueError(decision.reason_codes[0])
        if "research" not in descriptor.admission.intended_uses:
            raise ValueError("SOURCE_USE_UNVERIFIED")
    return VerifiedSourceRegistry(
        validated,
        admission,
        registered_adapter_ids=frozenset({"rss_atom", "hacker_news", "arxiv", "gdelt"}),
        intended_use="research",
    )


__all__ = ["build_local_source_registry"]

"""运营 Profile、事实权威性和最小上下文契约。

本模块只保存不可变的声明性资料，不读取外部来源，也不把候选值提升为已确认事实。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from enum import StrEnum

from efficiency_platform_agent.core.run import JsonObject

from .task import OperationTaskSpec, SourceScope

_STABLE_ID = re.compile(r"[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?")
_SEMANTIC_VERSION = re.compile(
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)


class ProfileKind(StrEnum):
    """运营上下文支持的七类 Profile。"""

    BRAND = "brand"
    IP = "ip"
    PRODUCT = "product"
    AUDIENCE = "audience"
    METRIC = "metric"
    CHANNEL = "channel"
    CAMPAIGN = "campaign"


class ProfileFactState(StrEnum):
    """事实在权威链中的状态。"""

    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"


def _stable_id(field_name: str, value: str) -> None:
    if not isinstance(value, str) or _STABLE_ID.fullmatch(value) is None:
        raise ValueError(f"{field_name}必须是稳定的小写标识")


def _non_empty(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name}不能为空")


def _semantic_version(field_name: str, value: str) -> None:
    if not isinstance(value, str) or _SEMANTIC_VERSION.fullmatch(value) is None:
        raise ValueError(f"{field_name}必须使用MAJOR.MINOR.PATCH")


def _tuple_of_facts(value: tuple[ProfileFact, ...]) -> None:
    if not isinstance(value, tuple):
        raise TypeError("facts必须是不可变元组")
    ids: set[str] = set()
    for fact in value:
        if not isinstance(fact, ProfileFact):
            raise TypeError("facts只能包含ProfileFact")
        if fact.fact_id in ids:
            raise ValueError("facts中的fact_id不能重复")
        ids.add(fact.fact_id)


@dataclass(frozen=True, slots=True)
class ProfileFact:
    """带来源和确认状态的单条 Profile 事实。"""

    fact_id: str
    field_name: str
    value: JsonObject
    source_kind: SourceScope
    source_reference: str
    state: ProfileFactState
    confirmed_at_epoch_ms: int | None
    expires_at_epoch_ms: int | None

    def __post_init__(self) -> None:
        _stable_id("fact_id", self.fact_id)
        _non_empty("field_name", self.field_name)
        if not isinstance(self.value, JsonObject):
            raise TypeError("value必须是JsonObject")
        if not isinstance(self.source_kind, SourceScope):
            raise TypeError("source_kind必须是SourceScope")
        _non_empty("source_reference", self.source_reference)
        if not isinstance(self.state, ProfileFactState):
            raise TypeError("state必须是ProfileFactState")
        for name, value in (
            ("confirmed_at_epoch_ms", self.confirmed_at_epoch_ms),
            ("expires_at_epoch_ms", self.expires_at_epoch_ms),
        ):
            if value is not None and (not isinstance(value, int) or value < 0):
                raise ValueError(f"{name}必须是非负整数或空值")
        if (
            self.state is ProfileFactState.CANDIDATE
            and self.confirmed_at_epoch_ms is not None
        ):
            raise ValueError("候选事实不能带确认时间")
        if (
            self.state is ProfileFactState.CONFIRMED
            and self.confirmed_at_epoch_ms is None
        ):
            raise ValueError("已确认事实必须带确认时间")


def _validate_profile(
    contract_version: str,
    profile_id: str,
    tenant_id: str,
    semantic_version: str,
    facts: tuple[ProfileFact, ...],
) -> None:
    if contract_version != "profile/1":
        raise ValueError("contract_version必须为profile/1")
    _stable_id("profile_id", profile_id)
    _stable_id("tenant_id", tenant_id)
    _semantic_version("semantic_version", semantic_version)
    _tuple_of_facts(facts)


@dataclass(frozen=True, slots=True)
class BrandProfile:
    """品牌定位、价值、调性和用语事实。"""

    contract_version: str
    profile_id: str
    tenant_id: str
    semantic_version: str
    facts: tuple[ProfileFact, ...]

    def __post_init__(self) -> None:
        _validate_profile(
            self.contract_version,
            self.profile_id,
            self.tenant_id,
            self.semantic_version,
            self.facts,
        )


@dataclass(frozen=True, slots=True)
class IPProfile:
    """IP身份、人设、边界和表达风格事实。"""

    contract_version: str
    profile_id: str
    tenant_id: str
    semantic_version: str
    facts: tuple[ProfileFact, ...]
    identity_state: str

    def __post_init__(self) -> None:
        _validate_profile(
            self.contract_version,
            self.profile_id,
            self.tenant_id,
            self.semantic_version,
            self.facts,
        )
        _non_empty("identity_state", self.identity_state)


@dataclass(frozen=True, slots=True)
class ProductProfile:
    """产品事实、卖点、受众和使用场景。"""

    contract_version: str
    profile_id: str
    tenant_id: str
    semantic_version: str
    facts: tuple[ProfileFact, ...]
    product_id: str

    def __post_init__(self) -> None:
        _validate_profile(
            self.contract_version,
            self.profile_id,
            self.tenant_id,
            self.semantic_version,
            self.facts,
        )
        _stable_id("product_id", self.product_id)


@dataclass(frozen=True, slots=True)
class AudienceProfile:
    """受众特征、需求、痛点和内容偏好。"""

    contract_version: str
    profile_id: str
    tenant_id: str
    semantic_version: str
    facts: tuple[ProfileFact, ...]
    segment_id: str

    def __post_init__(self) -> None:
        _validate_profile(
            self.contract_version,
            self.profile_id,
            self.tenant_id,
            self.semantic_version,
            self.facts,
        )
        _stable_id("segment_id", self.segment_id)


@dataclass(frozen=True, slots=True)
class MetricProfile:
    """指标定义、口径、目标和周期，不保存实际运营结果。"""

    contract_version: str
    profile_id: str
    tenant_id: str
    semantic_version: str
    facts: tuple[ProfileFact, ...]
    metric_id: str
    definition: str
    target_value: JsonObject | None
    period: str

    def __post_init__(self) -> None:
        _validate_profile(
            self.contract_version,
            self.profile_id,
            self.tenant_id,
            self.semantic_version,
            self.facts,
        )
        _stable_id("metric_id", self.metric_id)
        _non_empty("definition", self.definition)
        if self.target_value is not None and not isinstance(
            self.target_value, JsonObject
        ):
            raise TypeError("target_value必须是JsonObject或空值")
        _non_empty("period", self.period)


@dataclass(frozen=True, slots=True)
class ChannelProfile:
    """渠道结构、语气、篇幅和排版规则的版本化声明。"""

    contract_version: str
    profile_id: str
    tenant_id: str
    channel_id: str
    rules_version: str
    rules: JsonObject
    facts: tuple[ProfileFact, ...]
    semantic_version: str = "1.0.0"

    def __post_init__(self) -> None:
        _validate_profile(
            self.contract_version,
            self.profile_id,
            self.tenant_id,
            self.semantic_version,
            self.facts,
        )
        _stable_id("channel_id", self.channel_id)
        _non_empty("rules_version", self.rules_version)
        if not isinstance(self.rules, JsonObject):
            raise TypeError("rules必须是JsonObject")


@dataclass(frozen=True, slots=True)
class CampaignProfile:
    """活动目标、主题、周期、资源、机制和风险事实。"""

    contract_version: str
    profile_id: str
    tenant_id: str
    semantic_version: str
    facts: tuple[ProfileFact, ...]
    campaign_id: str

    def __post_init__(self) -> None:
        _validate_profile(
            self.contract_version,
            self.profile_id,
            self.tenant_id,
            self.semantic_version,
            self.facts,
        )
        _stable_id("campaign_id", self.campaign_id)


Profile = (
    BrandProfile
    | IPProfile
    | ProductProfile
    | AudienceProfile
    | MetricProfile
    | ChannelProfile
    | CampaignProfile
)


@dataclass(frozen=True, slots=True)
class ProfileReference:
    """任务上下文中对 Profile 版本及事实的最小引用。"""

    profile_id: str
    kind: ProfileKind
    semantic_version: str
    fact_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _stable_id("profile_id", self.profile_id)
        if not isinstance(self.kind, ProfileKind):
            raise TypeError("kind必须是ProfileKind")
        _semantic_version("semantic_version", self.semantic_version)
        if not isinstance(self.fact_ids, tuple):
            raise TypeError("fact_ids必须是不可变元组")
        for fact_id in self.fact_ids:
            _stable_id("fact_id", fact_id)
        if len(set(self.fact_ids)) != len(self.fact_ids):
            raise ValueError("fact_ids不能重复")


@dataclass(frozen=True, slots=True)
class OperationContext:
    """仅包含任务所需 Profile 引用和来源范围的最小运营上下文。"""

    contract_version: str
    context_id: str
    tenant_id: str
    task_id: str
    profile_references: tuple[ProfileReference, ...]
    source_scope_ids: frozenset[SourceScope]

    def __post_init__(self) -> None:
        if self.contract_version != "operation-context/1":
            raise ValueError("contract_version必须为operation-context/1")
        _stable_id("context_id", self.context_id)
        _stable_id("tenant_id", self.tenant_id)
        _stable_id("task_id", self.task_id)
        if not isinstance(self.profile_references, tuple):
            raise TypeError("profile_references必须是不可变元组")
        profile_ids: set[str] = set()
        for reference in self.profile_references:
            if not isinstance(reference, ProfileReference):
                raise TypeError("profile_references只能包含ProfileReference")
            if reference.profile_id in profile_ids:
                raise ValueError("profile_references中的profile_id不能重复")
            profile_ids.add(reference.profile_id)
        if not isinstance(self.source_scope_ids, frozenset):
            raise TypeError("source_scope_ids必须是不可变集合")
        if any(not isinstance(scope, SourceScope) for scope in self.source_scope_ids):
            raise TypeError("source_scope_ids只能包含SourceScope")

    @property
    def profiles(self) -> tuple[ProfileReference, ...]:
        """兼容冻结接口中曾使用的简短字段名。"""
        return self.profile_references


def _profile_kind(profile: Profile) -> ProfileKind:
    if isinstance(profile, BrandProfile):
        return ProfileKind.BRAND
    if isinstance(profile, IPProfile):
        return ProfileKind.IP
    if isinstance(profile, ProductProfile):
        return ProfileKind.PRODUCT
    if isinstance(profile, AudienceProfile):
        return ProfileKind.AUDIENCE
    if isinstance(profile, MetricProfile):
        return ProfileKind.METRIC
    if isinstance(profile, ChannelProfile):
        return ProfileKind.CHANNEL
    if isinstance(profile, CampaignProfile):
        return ProfileKind.CAMPAIGN
    raise TypeError("仅支持七类运营Profile")


def _profile_is_current(profile: Profile, now_epoch_ms: int | None = None) -> bool:
    """只接受没有过期确认事实的 Profile；候选事实不会被提升为确认事实。"""
    current = int(time.time() * 1000) if now_epoch_ms is None else now_epoch_ms
    return all(
        fact.state is not ProfileFactState.EXPIRED
        and not (
            fact.expires_at_epoch_ms is not None and fact.expires_at_epoch_ms <= current
        )
        for fact in profile.facts
    )


def select_profiles_for_task(
    task: OperationTaskSpec,
    profile_candidates: tuple[Profile, ...],
) -> OperationContext:
    """按任务 domains 选择租户隔离、版本有效的最小 Profile 上下文。"""
    if not isinstance(task, OperationTaskSpec):
        raise TypeError("task必须是OperationTaskSpec")
    if not isinstance(profile_candidates, tuple):
        raise TypeError("profile_candidates必须是不可变元组")
    required = {
        kind
        for kind in ProfileKind
        if any(domain.value == kind.value for domain in task.domains)
    }
    selected: list[Profile] = []
    seen: set[ProfileKind] = set()
    for profile in profile_candidates:
        kind = _profile_kind(profile)
        if profile.tenant_id != task.tenant_id:
            raise ValueError("Profile租户与TaskSpec不一致")
        if kind not in required:
            raise ValueError("Profile未被任务请求")
        if kind in seen:
            raise ValueError("同一Profile类型只能提供一个版本")
        if not _profile_is_current(profile):
            raise ValueError("Profile包含过期事实")
        selected.append(profile)
        seen.add(kind)
    missing = required - seen
    if missing:
        raise ValueError("任务所需Profile缺失")
    if ProfileKind.CHANNEL in seen and not any(
        isinstance(item, ChannelProfile) for item in selected
    ):
        raise ValueError("渠道Profile无效")
    refs = tuple(
        ProfileReference(
            profile_id=profile.profile_id,
            kind=_profile_kind(profile),
            semantic_version=profile.semantic_version,
            fact_ids=tuple(fact.fact_id for fact in profile.facts),
        )
        for profile in selected
    )
    scopes = frozenset(
        fact.source_kind for profile in selected for fact in profile.facts
    )
    return OperationContext(
        contract_version="operation-context/1",
        context_id=f"context-{task.task_id}",
        tenant_id=task.tenant_id,
        task_id=task.task_id,
        profile_references=refs,
        source_scope_ids=scopes,
    )

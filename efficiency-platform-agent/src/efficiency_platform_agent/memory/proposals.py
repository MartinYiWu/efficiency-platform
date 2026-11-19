"""已冻结用途内的候选CPU校验；确认、抑制复核和持久化仍由Java负责。"""

from dataclasses import dataclass, field
from typing import Literal

from efficiency_platform_agent.contracts.memory import (
    ConversationScopeModel,
    MemoryProposalModel,
    SourceDependencyModel,
)
from efficiency_platform_agent.core.context_control import (
    ContextFragmentCounter,
    ModelCapacity,
)
from efficiency_platform_agent.core.memory import MemoryPolicy, require_id
from efficiency_platform_agent.core.run import ProviderMessage
from efficiency_platform_agent.memory.conflicts import (
    CurrentFieldValue,
    ProposalAction,
    classify_field,
)
from efficiency_platform_agent.memory.packet_reader import PREFERENCE_VALUES
from efficiency_platform_agent.memory.summary_contracts import SummaryInputSource
from efficiency_platform_agent.memory.summary_policy import SummaryPolicy


@dataclass(frozen=True, slots=True)
class ProposalTaskState:
    """由原认证frame的当前Java来源/抑制快照构造，不接收模型声明。"""

    scope: ConversationScopeModel
    task_id: str
    policy: MemoryPolicy
    sources: tuple[SummaryInputSource, ...] = field(repr=False)
    current_values: tuple[CurrentFieldValue, ...] = field(repr=False)
    suppressed_fields: frozenset[str]
    suppressed_sources: frozenset[tuple[str, str]]
    replacement_item_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        require_id(self.task_id)
        if (
            type(self.scope) is not ConversationScopeModel
            or type(self.policy) is not MemoryPolicy
            or type(self.sources) is not tuple
            or type(self.current_values) is not tuple
            or any(type(item) is not CurrentFieldValue for item in self.current_values)
            or any(
                type(values) is not frozenset
                for values in (
                    self.suppressed_fields,
                    self.suppressed_sources,
                    self.replacement_item_ids,
                )
            )
        ):
            raise ValueError("PROPOSAL_TRUSTED_STATE_REQUIRED")
        if not self.replacement_item_ids.issubset(
            {item.item_id for item in self.current_values}
        ):
            raise ValueError("PROPOSAL_REPLACEMENT_UNKNOWN")


@dataclass(frozen=True, slots=True)
class EvaluatedProposal:
    kind: str
    field_key: str
    value: str = field(repr=False)
    action: ProposalAction
    source_dependencies: tuple[SourceDependencyModel, ...] = field(repr=False)
    existing_item_ids: tuple[str, ...]
    expected_item_revisions: tuple[int, ...]
    decision_status: Literal["PROPOSED"] = field(default="PROPOSED", init=False)
    index_status: Literal["NOT_REQUESTED"] = field(default="NOT_REQUESTED", init=False)


def evaluate_proposals(
    candidates: tuple[MemoryProposalModel, ...],
    state: ProposalTaskState,
    counter: ContextFragmentCounter,
    capacity: ModelCapacity,
    *,
    now: int,
) -> tuple[EvaluatedProposal, ...]:
    if type(candidates) is not tuple or len(candidates) > 16:
        raise ValueError("PROPOSAL_COUNT_LIMIT")
    policy = state.policy
    if (
        not policy.enabled
        or not policy.auto_extract
        or state.scope.domain != policy.domain
        or state.scope.top_level_agent_id not in policy.agent_ids
        or "USER_PRIVATE" not in policy.allowed_scopes
        or state.scope.domain == "hr"
    ):
        raise ValueError("PROPOSAL_POLICY_DENIED")
    SummaryPolicy().admit("PROPOSALS", state.sources, state.scope, now=now)
    dependencies = tuple(
        dict.fromkeys(dep for src in state.sources for dep in src.source_dependencies)
    )
    if any(
        (dep.source_type, dep.source_id) in state.suppressed_sources
        for dep in dependencies
    ):
        raise ValueError("PROPOSAL_SOURCE_SUPPRESSED")
    unique: dict[tuple[str, str, str], MemoryProposalModel] = {}
    for candidate in candidates:
        if type(candidate) is not MemoryProposalModel:
            raise ValueError("PROPOSAL_CANDIDATE_INVALID")
        if (
            candidate.kind not in policy.writable_kinds
            or candidate.field_key not in policy.field_allowlist
        ):
            raise ValueError("PROPOSAL_FIELD_DENIED")
        if candidate.field_key in state.suppressed_fields:
            raise ValueError("PROPOSAL_FIELD_SUPPRESSED")
        if (
            candidate.kind == "PREFERENCE"
            and candidate.value
            not in PREFERENCE_VALUES.get(candidate.field_key, frozenset())
        ):
            raise ValueError("PROPOSAL_VALUE_DENIED")
        measurement = counter.measure_messages(
            (ProviderMessage("user", candidate.value),), capacity
        )
        if not measurement.verified or measurement.total_upper_bound > 512:
            raise ValueError("PROPOSAL_TOKEN_LIMIT")
        unique[(candidate.kind, candidate.field_key, candidate.value)] = candidate
    results = []
    for (kind, key, value), candidate in unique.items():
        current = tuple(
            item
            for item in state.current_values
            if (item.kind, item.field_key) == (kind, key)
        )
        competing = frozenset(v for k, f, v in unique if (k, f) == (kind, key))
        results.append(
            EvaluatedProposal(
                kind,
                key,
                value,
                classify_field(value, current, competing, state.replacement_item_ids),
                dependencies,
                tuple(item.item_id for item in current),
                tuple(item.revision for item in current),
            )
        )
    return tuple(results)

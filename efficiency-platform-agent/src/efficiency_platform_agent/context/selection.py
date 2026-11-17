"""只缩小已授权输入的有界、确定性 CPU 选择器。"""

from dataclasses import dataclass, field, replace

from efficiency_platform_agent.context.budget import evaluate_window, window_pressure
from efficiency_platform_agent.context.policy import ContextPiece, ContextPolicy
from efficiency_platform_agent.core.context_control import (
    ContextFragmentCounter,
    ModelCapacity,
    TokenCounter,
    TokenMeasurement,
    WindowDecision,
    WindowLimits,
)
from efficiency_platform_agent.core.memory import ExecutionScope, SourceDependency
from efficiency_platform_agent.core.run import ProviderMessage, ProviderRequest


@dataclass(frozen=True, slots=True)
class ContextView:
    pieces: tuple[ContextPiece, ...] = field(repr=False)
    messages: tuple[ProviderMessage, ...] = field(repr=False)
    request: ProviderRequest = field(repr=False)
    selected_safety_dependencies: tuple[SourceDependency, ...]
    exclusions: tuple[tuple[str, str], ...]
    decision: WindowDecision
    measurement: TokenMeasurement
    before_measurement: TokenMeasurement
    pressure: str


def select_context(
    scope: ExecutionScope,
    policy: ContextPolicy,
    sources: tuple[ContextPiece, ...],
    limits: WindowLimits,
    *,
    counter: TokenCounter,
    capacity: ModelCapacity,
    request_template: ProviderRequest,
) -> ContextView:
    if not isinstance(scope, ExecutionScope) or policy.scope != scope:
        raise ValueError("CONTEXT_SCOPE_INVALID")
    if type(sources) is not tuple or any(
        not isinstance(p, ContextPiece) for p in sources
    ):
        raise TypeError("CONTEXT_SOURCES_INVALID")
    if len(sources) > policy.max_pieces:
        raise ValueError("CONTEXT_SOURCE_LIMIT")
    if len({p.piece_id for p in sources}) != len(sources):
        raise ValueError("CONTEXT_PIECE_ID_DUPLICATE")
    if tuple(m for p in sources for m in p.messages) != request_template.messages:
        raise ValueError("CONTEXT_TEMPLATE_MISMATCH")
    if (
        not capacity.verified
        or limits.context_window_tokens > capacity.context_window_tokens
        or limits.output_reserve_tokens > capacity.max_output_tokens
        or (
            capacity.max_input_tokens is not None
            and limits.input_cap() > capacity.max_input_tokens
        )
    ):
        raise ValueError("CONTEXT_CAPACITY_UNVERIFIED")

    exclusions: list[tuple[str, str]] = []
    authorized: list[ContextPiece] = []
    for piece in sources:
        reason = None
        if piece.scope != scope:
            reason = "SCOPE_MISMATCH"
        elif not set(piece.safety_dependencies).issubset(
            policy.authorized_dependencies
        ):
            reason = "SOURCE_NOT_AUTHORIZED"
        elif not set(piece.covered_message_ids).issubset(policy.allowed_message_ids):
            reason = "RANGE_NOT_AUTHORIZED"
        elif (
            piece.kind in {"history", "summary"}
            and scope.conversation.session_kind == "TASK_ONLY"
        ):
            reason = "TASK_ONLY_HISTORY_DISABLED"
        elif (
            piece.kind in {"history", "memory", "summary"}
            and not piece.safety_dependencies
        ):
            reason = "SOURCE_DEPENDENCIES_REQUIRED"
        elif piece.kind in {"history", "summary"} and not piece.covered_message_ids:
            reason = "SOURCE_RANGE_REQUIRED"
        if reason:
            if piece.is_required:
                raise ValueError("CONTEXT_SOURCE_NOT_AUTHORIZED")
            exclusions.append((piece.piece_id, reason))
        else:
            authorized.append(piece)

    selected: list[ContextPiece] = []
    candidates: list[ContextPiece] = []
    covered: set[str] = set()
    call_ids: set[str] = set()
    # 必保先去重，后处理可选内容，防止可选摘要挤掉当前原文。
    ordered = sorted(
        authorized, key=lambda p: (not p.is_required, -p.priority, sources.index(p))
    )
    for piece in ordered:
        overlap = covered.intersection(piece.covered_message_ids)
        duplicate = next(
            (
                p
                for p in selected + candidates
                if p.messages == piece.messages
                and p.safety_dependencies == piece.safety_dependencies
                and p.covered_message_ids == piece.covered_message_ids
            ),
            None,
        )
        if overlap or duplicate:
            if piece.is_required and not duplicate:
                raise ValueError("CONTEXT_REQUIRED_COVERAGE_CONFLICT")
            exclusions.append((piece.piece_id, "DUPLICATE_COVERAGE"))
            continue
        piece_call_ids = {
            call.tool_call_id
            for message in piece.messages
            for call in message.tool_calls
        }
        if call_ids.intersection(piece_call_ids):
            raise ValueError("CONTEXT_TOOL_GROUP_INVALID")
        call_ids.update(piece_call_ids)
        covered.update(piece.covered_message_ids)
        (selected if piece.is_required else candidates).append(piece)
    if not selected:
        raise ValueError("CONTEXT_REQUIRED_INPUT_MISSING")

    def request_for(pieces: list[ContextPiece]) -> ProviderRequest:
        ordered_pieces = sorted(pieces, key=sources.index)
        return replace(
            request_template,
            messages=tuple(m for p in ordered_pieces for m in p.messages),
        )

    def measure(pieces: list[ContextPiece]) -> TokenMeasurement:
        measurement = counter.measure(request_for(pieces), capacity)
        if not isinstance(measurement, TokenMeasurement) or not measurement.verified:
            raise ValueError("CONTEXT_CAPACITY_UNVERIFIED")
        return measurement

    def measure_slot(pieces: list[ContextPiece]) -> TokenMeasurement:
        if not isinstance(counter, ContextFragmentCounter):
            return measure(pieces)
        measurement = counter.measure_messages(request_for(pieces).messages, capacity)
        if not isinstance(measurement, TokenMeasurement) or not measurement.verified:
            raise ValueError("CONTEXT_CAPACITY_UNVERIFIED")
        return measurement

    fixed = measure(selected).total_upper_bound
    before = measure(selected + candidates)
    slot_limits = {
        "history": policy.history_token_limit,
        "memory": min(policy.memory_token_limit, limits.input_cap() // 5),
        "summary": policy.summary_token_limit,
        "capsule": policy.capsule_token_limit,
    }
    if fixed <= limits.input_cap():
        for piece in candidates:
            same_kind = [
                p for p in selected if not p.is_required and p.kind == piece.kind
            ]
            if (
                piece.kind == "history"
                and sum(len(p.messages) for p in same_kind + [piece])
                > policy.max_history_messages
            ):
                exclusions.append((piece.piece_id, "SLOT_LIMIT"))
                continue
            if (
                piece.kind == "summary"
                and measure_slot([piece]).total_upper_bound > 500
            ):
                exclusions.append((piece.piece_id, "SLOT_LIMIT"))
                continue
            slot_limit = slot_limits.get(piece.kind)
            if (
                slot_limit is not None
                and measure_slot(same_kind + [piece]).total_upper_bound > slot_limit
            ):
                exclusions.append((piece.piece_id, "SLOT_LIMIT"))
                continue
            if measure(selected + [piece]).total_upper_bound > limits.input_cap():
                exclusions.append((piece.piece_id, "WINDOW_LIMIT"))
                continue
            selected.append(piece)
    else:
        exclusions.extend((p.piece_id, "REQUIRED_OVERFLOW") for p in candidates)
    selected.sort(key=sources.index)
    request = request_for(selected)
    measurement = measure(selected)
    dependencies = tuple(
        dict.fromkeys(d for p in selected for d in p.safety_dependencies)
    )
    return ContextView(
        tuple(selected),
        request.messages,
        request,
        dependencies,
        tuple(exclusions),
        evaluate_window(limits, measurement.total_upper_bound, fixed),
        measurement,
        before,
        window_pressure(limits, measurement.total_upper_bound),
    )

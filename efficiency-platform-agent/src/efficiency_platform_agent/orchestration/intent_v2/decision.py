"""Intent V2 的确定性准入与单问题澄清策略。"""

from __future__ import annotations

from efficiency_platform_agent.contracts.intent_v2 import (
    CapabilityPlanV2,
    IntentDecision,
    IntentFrameV2,
)

_TECHNICAL_REASONS = frozenset(
    {
        "CAPABILITY_SCHEMA_UNKNOWN",
        "BINDING_INTERNAL_ERROR",
    }
)
_UNSUPPORTED_REASONS = frozenset(
    {
        "CAPABILITY_UNKNOWN",
        "CAPABILITY_UNAVAILABLE",
        "CAPABILITY_PARAMETER_INVALID",
    }
)
_CLARIFICATION_PRIORITY = (
    "goal",
    "object",
    "topic",
    "entities",
    "reference",
    "temporal",
    "source_constraints",
    "output_requirements",
)
_KNOWN_CLARIFICATION_FIELDS = frozenset((*_CLARIFICATION_PRIORITY, "exclusions"))


class IntentDecisionPolicyV2:
    """按技术、支持性、歧义和完整性固定顺序决定准入。"""

    def decide(
        self,
        frame: IntentFrameV2,
        binding: CapabilityPlanV2,
    ) -> IntentDecision:
        if not isinstance(frame, IntentFrameV2):
            raise TypeError("frame 必须是 IntentFrameV2")
        if not isinstance(binding, CapabilityPlanV2):
            raise TypeError("binding 必须是 CapabilityPlanV2")
        reasons = tuple(binding.reason_codes)
        reason_roots = {_reason_root(item) for item in reasons}
        technical = tuple(
            item for item in reasons if _reason_root(item) in _TECHNICAL_REASONS
        )
        if technical:
            return IntentDecision(outcome="FAILED", reason_codes=technical)
        unsupported = tuple(
            item for item in reasons if _reason_root(item) in _UNSUPPORTED_REASONS
        )
        if unsupported:
            return IntentDecision(outcome="UNSUPPORTED", reason_codes=unsupported)
        if not binding.supported and not reason_roots <= {"REQUIRED_FIELD_MISSING"}:
            return IntentDecision(
                outcome="FAILED",
                reason_codes=reasons or ("BINDING_INTERNAL_ERROR",),
            )

        unknown_fields = _unknown_clarification_fields(frame, reasons)
        if unknown_fields:
            return IntentDecision(
                outcome="FAILED",
                reason_codes=("INTENT_AMBIGUITY_FIELD_UNKNOWN",),
            )

        clarification_reasons, fields = _clarification_candidates(frame, reasons)
        if not frame.goal_nodes and frame.dialog_act not in {"chat", "cancel"}:
            clarification_reasons.append("REQUIRED_FIELD_MISSING:goal")
            fields.add("goal")
        if fields:
            selected = _highest_priority(fields)
            selected_reasons = tuple(
                item
                for item in clarification_reasons
                if _field_from_reason(item) == selected
            ) or (f"INTENT_AMBIGUOUS:{selected}",)
            return IntentDecision(
                outcome="CLARIFY",
                reason_codes=selected_reasons,
                clarification_fields=(selected,),
            )

        if frame.goal_nodes:
            planned = {step.goal_id for step in binding.steps}
            expected = {goal.goal_id for goal in frame.goal_nodes}
            if not binding.supported or planned != expected:
                return IntentDecision(
                    outcome="FAILED",
                    reason_codes=("CAPABILITY_PLAN_INCOMPLETE",),
                )
        return IntentDecision(outcome="READY")


def _clarification_candidates(
    frame: IntentFrameV2,
    binding_reasons: tuple[str, ...],
) -> tuple[list[str], set[str]]:
    reasons: list[str] = []
    fields: set[str] = set()
    for reason in binding_reasons:
        if _reason_root(reason) == "REQUIRED_FIELD_MISSING":
            field_name = _field_from_reason(reason)
            if field_name is not None:
                reasons.append(reason)
                fields.add(field_name)
    for ambiguity in frame.ambiguities:
        if ambiguity.blocking:
            fields.add(ambiguity.field_name)
            reasons.append(f"INTENT_AMBIGUOUS:{ambiguity.field_name}")
    if frame.unresolved_references:
        fields.add("reference")
        reasons.append("INTENT_REFERENCE_AMBIGUOUS:reference")
    for field_name in (
        "topic",
        "entities",
        "exclusions",
        "temporal",
        "source_constraints",
        "output_requirements",
    ):
        value = getattr(frame, field_name)
        if value is not None and value.validation in {"ambiguous", "invalid"}:
            fields.add(field_name)
            reasons.append(f"INTENT_AMBIGUOUS:{field_name}")
    return reasons, fields


def _highest_priority(fields: set[str]) -> str:
    for field_name in _CLARIFICATION_PRIORITY:
        if field_name in fields:
            return field_name
    return min(fields)


def _unknown_clarification_fields(
    frame: IntentFrameV2,
    binding_reasons: tuple[str, ...],
) -> set[str]:
    supplied = {
        ambiguity.field_name for ambiguity in frame.ambiguities if ambiguity.blocking
    }
    supplied.update(
        field_name
        for reason in binding_reasons
        if _reason_root(reason) == "REQUIRED_FIELD_MISSING"
        if (field_name := _field_from_reason(reason)) is not None
    )
    return supplied - _KNOWN_CLARIFICATION_FIELDS


def _reason_root(reason: str) -> str:
    return reason.split(":", 1)[0]


def _field_from_reason(reason: str) -> str | None:
    parts = reason.split(":", 1)
    return parts[1] if len(parts) == 2 and parts[1] else None


__all__ = ["IntentDecisionPolicyV2"]

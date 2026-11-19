"""摘要v2短引用投影；权限、完整身份和确认事实始终由原受信快照保存。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from efficiency_platform_agent.memory.summary_contracts import (
    RejectedOption,
    SummaryBasisEvent,
    SummaryEntry,
    SummaryInputSource,
    SummarySegment,
    SummaryWatermark,
)

SUMMARY_LEGEND = (
    "Summary v2: g=goal,c=confirmed constraints,d=decisions,r=rejected,q=open questions,i=references,u=uncertainties. "
    "Rows=[claim,text,origin,status,sources,basis,critical?,reason?]. "
    "Origin:0=user requirement,1=business fact,2=model suggestion,3=unconfirmed inference. "
    "Status:0=proposed,1=confirmed,2=rejected,3=unresolved. "
    "Critical=[field,kind(0=number,1=date,2=constraint),value,timezone]. "
    "Claim/source/basis numbers are opaque references bound to authorized metadata. Never promote suggestions or unresolved content."
)
ORIGINS = (
    "USER_REQUIREMENT",
    "BUSINESS_FACT",
    "MODEL_SUGGESTION",
    "UNCONFIRMED_INFERENCE",
)
STATUSES = ("PROPOSED", "CONFIRMED", "REJECTED", "UNRESOLVED")
KINDS = ("NUMBER", "DATE", "CONSTRAINT")
SLOTS = (
    ("g", "goal"),
    ("c", "confirmed_constraints"),
    ("d", "decisions"),
    ("r", "rejected_options"),
    ("q", "open_questions"),
    ("i", "important_refs"),
    ("u", "uncertainties"),
)


class _Output(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )


class Narrative(_Output):
    text: str = Field(min_length=1, max_length=2048, repr=False)
    sources: tuple[str, ...] = Field(min_length=1, max_length=128)


class Note(Narrative):
    kind: Literal["suggestion", "question", "reference", "uncertainty"]


class DeriveText(_Output):
    v: Literal[2]
    goal: Narrative
    notes: tuple[Note, ...] = Field(max_length=128)
    kept: tuple[str, ...] = Field(max_length=897)


@dataclass(frozen=True, slots=True)
class ModelProjection:
    user_json: str = field(repr=False)
    aliases_json: str = field(repr=False)
    sources: tuple[SummaryInputSource, ...] = field(repr=False)
    events: tuple[SummaryBasisEvent, ...] = field(repr=False)
    required: tuple[SummaryEntry | RejectedOption, ...] = field(repr=False)
    source_revision: int

    def candidate(self, raw: str, operation_id: str) -> SummarySegment:
        output = DeriveText.model_validate_json(raw)
        expected = tuple(f"r{i}" for i in range(len(self.required)))
        if output.kept != expected:
            raise ValueError("SUMMARY_REQUIRED_STATE_CHANGED")
        source_aliases = {
            f"s{i}": source.source_ref for i, source in enumerate(self.sources)
        }

        def narrative(
            item: Narrative, claim: str, suggestion: bool = False
        ) -> SummaryEntry:
            if len(set(item.sources)) != len(item.sources) or any(
                alias not in source_aliases for alias in item.sources
            ):
                raise ValueError("SUMMARY_SOURCE_REF_UNKNOWN")
            return SummaryEntry(
                claim_ref=claim,
                text=item.text,
                content_origin="MODEL_SUGGESTION"
                if suggestion
                else "UNCONFIRMED_INFERENCE",
                decision_status="PROPOSED" if suggestion else "UNRESOLVED",
                source_refs=tuple(source_aliases[alias] for alias in item.sources),
                basis_event_ref=None,
            )

        used_claims = {entry.claim_ref for entry in self.required}

        def claim(index: int) -> str:
            candidate = "narrative:" + str(index)
            while candidate in used_claims:
                candidate = "unconfirmed:" + candidate
            used_claims.add(candidate)
            return candidate

        slots: dict[str, list] = {name: [] for _, name in SLOTS if name != "goal"}
        for entry in self.required:
            if entry.decision_status == "REJECTED":
                if not isinstance(entry, RejectedOption):
                    event = next(
                        (
                            e
                            for e in self.events
                            if e.event_ref == entry.basis_event_ref
                        ),
                        None,
                    )
                    if event is None:
                        raise ValueError("SUMMARY_CONFIRMATION_REQUIRED")
                    entry = RejectedOption(
                        **entry.model_dump(), reason=event.rejection_reason
                    )
                slots["rejected_options"].append(entry)
            else:
                target = {
                    "CONFIRMED": "confirmed_constraints",
                    "PROPOSED": "decisions",
                    "UNRESOLVED": "uncertainties",
                }[entry.decision_status]
                slots[target].append(entry)
        targets = {
            "suggestion": "decisions",
            "question": "open_questions",
            "reference": "important_refs",
            "uncertainty": "uncertainties",
        }
        for index, note in enumerate(output.notes):
            slots[targets[note.kind]].append(
                narrative(note, claim(index + 1), note.kind == "suggestion")
            )
        dependencies = tuple(
            dict.fromkeys(
                d for source in self.sources for d in source.source_dependencies
            )
        )
        return SummarySegment(
            segment_id="summary-" + hashlib.sha256(operation_id.encode()).hexdigest(),
            scope=self.sources[0].scope,
            covered_sources=tuple(s.source_ref for s in self.sources),
            watermark=SummaryWatermark(
                source_revision=self.source_revision,
                first_sequence=self.sources[0].sequence,
                last_sequence=self.sources[-1].sequence,
            ),
            goal=narrative(output.goal, claim(0)),
            source_dependencies=dependencies,
            expires_at=min(s.expires_at for s in self.sources),
            **{name: tuple(entries) for name, entries in slots.items()},
        )


def project_model_sources(
    sources, bodies, events, required, source_revision
) -> ModelProjection:
    if not sources or len(sources) != len(bodies) or not required:
        raise ValueError("SUMMARY_SOURCE_PROJECTION_REQUIRED")
    refs = {source.source_ref: f"s{i}" for i, source in enumerate(sources)}
    if len(refs) != len(sources):
        raise ValueError("SUMMARY_SOURCES_DUPLICATE")
    groups = {
        group: f"g{i}"
        for i, group in enumerate(dict.fromkeys(s.group_id for s in sources))
    }
    event_refs = {event.event_ref: f"e{i}" for i, event in enumerate(events)}
    if len(event_refs) != len(events):
        raise ValueError("SUMMARY_BASIS_UNKNOWN")
    entries = []
    for index, entry in enumerate(required):
        if any(ref not in refs for ref in entry.source_refs) or (
            entry.basis_event_ref is not None
            and entry.basis_event_ref not in event_refs
        ):
            raise ValueError("SUMMARY_BASIS_SOURCE_MISMATCH")
        event = next((e for e in events if e.event_ref == entry.basis_event_ref), None)
        entries.append(
            {
                "ref": f"r{index}",
                "text": entry.text,
                "origin": entry.content_origin,
                "status": entry.decision_status,
                "sources": [refs[ref] for ref in entry.source_refs],
                "basis": event_refs.get(entry.basis_event_ref),
                "authority": event.authority if event else None,
                "critical": [
                    [v.field_ref, v.kind, v.value, v.timezone]
                    for v in entry.critical_values
                ],
                "reason": entry.reason if isinstance(entry, RejectedOption) else None,
            }
        )
    user = {
        "v": 2,
        "sources": [
            [refs[source.source_ref], groups[source.group_id], body]
            for source, body in zip(sources, bodies, strict=True)
        ],
        "required": entries,
    }
    mapping = {
        "v": 2,
        "sources": {alias: ref.model_dump(mode="json") for ref, alias in refs.items()},
        "events": {
            alias: ref.model_dump(mode="json") for ref, alias in event_refs.items()
        },
        "claims": {f"r{i}": entry.claim_ref for i, entry in enumerate(required)},
    }
    return ModelProjection(
        json.dumps(user, ensure_ascii=False, separators=(",", ":")),
        json.dumps(mapping, ensure_ascii=False, separators=(",", ":")),
        tuple(sources),
        tuple(events),
        tuple(required),
        source_revision,
    )


@dataclass(frozen=True, slots=True)
class RenderedSummary:
    text: str = field(repr=False)
    aliases_json: str = field(repr=False)


def render_summary(segment: SummarySegment) -> RenderedSummary:
    entries = tuple(
        entry
        for _, name in SLOTS
        for entry in ((segment.goal,) if name == "goal" else getattr(segment, name))
    )
    refs = tuple(
        dict.fromkeys(
            ref
            for entry in entries
            for ref in (
                *entry.source_refs,
                *((entry.basis_event_ref,) if entry.basis_event_ref else ()),
            )
        )
    )
    claims = tuple(dict.fromkeys(entry.claim_ref for entry in entries))
    payload: dict = {"v": 2}
    for short, name in SLOTS:
        selected = (segment.goal,) if name == "goal" else getattr(segment, name)
        if not selected:
            continue
        rows = []
        for entry in selected:
            row = [
                claims.index(entry.claim_ref),
                entry.text,
                ORIGINS.index(entry.content_origin),
                STATUSES.index(entry.decision_status),
                [refs.index(ref) for ref in entry.source_refs],
                refs.index(entry.basis_event_ref) if entry.basis_event_ref else None,
            ]
            if entry.critical_values or isinstance(entry, RejectedOption):
                row.append(
                    [
                        [v.field_ref, KINDS.index(v.kind), v.value, v.timezone]
                        for v in entry.critical_values
                    ]
                )
            if isinstance(entry, RejectedOption):
                row.append(entry.reason)
            rows.append(row)
        payload[short] = rows[0] if name == "goal" else rows
    aliases = {
        "v": 2,
        "references": [ref.model_dump(mode="json") for ref in refs],
        "claims": list(claims),
    }
    return RenderedSummary(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        json.dumps(aliases, ensure_ascii=False, separators=(",", ":")),
    )

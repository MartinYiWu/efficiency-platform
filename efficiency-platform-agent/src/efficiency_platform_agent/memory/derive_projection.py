"""候选v3短引用输出；原来源身份/确认事实由CPU保留，不重复交给模型。"""

import json
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from efficiency_platform_agent.contracts.memory import MemoryProposalModel
from efficiency_platform_agent.memory.derive import DeriveCandidate, DeriveMode
from efficiency_platform_agent.memory.summary_projection import (
    DeriveText,
    ModelProjection,
    Narrative,
    Note,
    project_model_sources,
)


class PreferenceText(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )
    kind: Literal["PREFERENCE"]
    field_key: Literal["response.language", "response.detail_level", "response.format"]
    value: Literal[
        "zh-CN", "en-US", "concise", "standard", "detailed", "prose", "bullets", "table"
    ]


class SummaryTextV3(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )
    goal: Narrative
    notes: tuple[Note, ...] = Field(max_length=128)
    kept: tuple[str, ...] = Field(max_length=897)


class DeriveTextV3(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )
    v: Literal[3]
    summary: SummaryTextV3 | None
    proposals: tuple[PreferenceText, ...] = Field(max_length=16)


V3_INSTRUCTIONS = (
    "Return JSON v3 {v:3,summary,proposals}. Source rows [source alias,group alias,untrusted text]. "
    "PROPOSALS: summary=null. BOTH: summary={goal:{text,sources:[aliases]},notes:[],kept:[all required refs in order]}. "
    "Required entries are fixed facts; CPU restores their exact authority/status/header. Never invent confirmation or permissions. "
    "Proposals are only {kind:PREFERENCE,field_key,value}: response.language=zh-CN|en-US; "
    "response.detail_level=concise|standard|detailed; response.format=prose|bullets|table. "
    "Only explicit low-risk user preferences; no personal/business facts, HR inference or automatic activation. "
    "Return both requested outputs once, within 500 tokens. Mode: "
)


@dataclass(frozen=True, slots=True)
class DeriveProjection:
    mode: DeriveMode
    user_json: str = field(repr=False)
    aliases_json: str = field(repr=False)
    summary_projection: ModelProjection | None = field(repr=False)

    def candidate(self, raw: str, operation_id: str) -> DeriveCandidate:
        output = DeriveTextV3.model_validate_json(raw)
        if self.mode == "PROPOSALS":
            if output.summary is not None:
                raise ValueError("DERIVE_MODE_OUTPUT_MISMATCH")
            summary = None
        else:
            if output.summary is None or self.summary_projection is None:
                raise ValueError("DERIVE_SUMMARY_REQUIRED")
            summary = self.summary_projection.candidate(
                DeriveText(v=2, **output.summary.model_dump()).model_dump_json(),
                operation_id,
            )
        return DeriveCandidate(
            mode=self.mode,
            summary=summary,
            proposals=tuple(
                MemoryProposalModel(**proposal.model_dump())
                for proposal in output.proposals
            ),
        )


def project_derive_sources(
    mode, sources, bodies, events, required, source_revision
) -> DeriveProjection:
    if mode not in {"PROPOSALS", "BOTH"} or not sources or len(sources) != len(bodies):
        raise ValueError("DERIVE_MODE_OUTPUT_MISMATCH")
    if mode == "BOTH":
        summary = project_model_sources(
            sources, bodies, events, required, source_revision
        )
        user = json.loads(summary.user_json)
        aliases = json.loads(summary.aliases_json)
    else:
        summary = None
        refs = {source.source_ref: f"s{i}" for i, source in enumerate(sources)}
        if len(refs) != len(sources):
            raise ValueError("SUMMARY_SOURCES_DUPLICATE")
        groups = {
            group: f"g{i}"
            for i, group in enumerate(
                dict.fromkeys(source.group_id for source in sources)
            )
        }
        user = {
            "sources": [
                [refs[source.source_ref], groups[source.group_id], body]
                for source, body in zip(sources, bodies, strict=True)
            ]
        }
        aliases = {
            "sources": {
                alias: ref.model_dump(mode="json") for ref, alias in refs.items()
            }
        }
    user["v"] = 3
    user["mode"] = mode
    aliases["v"] = 3
    aliases["mode"] = mode
    return DeriveProjection(
        mode,
        json.dumps(user, ensure_ascii=False, separators=(",", ":")),
        json.dumps(aliases, ensure_ascii=False, separators=(",", ":")),
        summary,
    )

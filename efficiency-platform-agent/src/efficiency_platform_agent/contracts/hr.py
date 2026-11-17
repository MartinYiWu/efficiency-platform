"""人事辅助能力的有界输入输出契约；不包含评分与授权策略。"""

import re
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from efficiency_platform_agent.contracts.memory_context import (
    MemoryContextEnvelope,
    MemoryContextInput,
)


class HrModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Offset(HrModel):
    clean_start: int = Field(ge=0)
    clean_end: int = Field(ge=0)
    source_start: int = Field(ge=0)
    source_end: int = Field(ge=0)


class Block(HrModel):
    block_id: str = Field(min_length=1, max_length=100)
    text: str = Field(max_length=100000)
    bbox: tuple[float, float, float, float] | None = None
    page: int | None = Field(default=None, ge=1, le=200)
    paragraph: int | None = Field(default=None, ge=1)
    source_start: int = Field(default=0, ge=0)
    offsets: list[Offset] = Field(default_factory=list)
    ocr_quality: float | None = Field(default=None, ge=0, le=1)


class Evidence(HrModel):
    block_id: str = Field(min_length=1, max_length=100)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1, max_length=1000)


class DateValue(HrModel):
    value: str = Field(min_length=4, max_length=10)
    precision: Literal["YEAR", "MONTH", "DAY"]
    source_text: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def valid_precision(self) -> "DateValue":
        length = {"YEAR": 4, "MONTH": 7, "DAY": 10}[self.precision]
        if len(self.value) != length:
            raise ValueError("日期精度与原文不符")
        date.fromisoformat(
            self.value + {"YEAR": "-01-01", "MONTH": "-01", "DAY": ""}[self.precision]
        )
        return self


class Measurement(HrModel):
    metric: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, max_length=100)
    value: Decimal | None = Field(default=None, ge=0)
    project_id: str = Field(min_length=1, max_length=100)
    role_level: int | None = Field(default=None, ge=1, le=3)
    managed_team_size: int | None = Field(default=None, ge=0, le=100000)


class Fact(HrModel):
    fact_id: str = Field(min_length=1, max_length=100)
    kind: Literal[
        "education",
        "employment",
        "project",
        "skill",
        "language",
        "certificate",
        "achievement",
    ]
    value: str = Field(min_length=1, max_length=3000)
    evidence: list[Evidence] = Field(min_length=1, max_length=5)
    organization: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    degree: str | None = Field(default=None, max_length=100)
    major: str | None = Field(default=None, max_length=200)
    start_date: DateValue | None = None
    end_date: DateValue | None = None
    ongoing: bool | None = None
    is_internship: bool | None = None
    measurement: Measurement | None = None
    background_claim: Literal["ENTREPRENEURSHIP", "CAREER_TRANSITION"] | None = None

    @model_validator(mode="after")
    def source_fields(self) -> "Fact":
        quotes = "\n".join(e.quote for e in self.evidence)
        if self.background_claim is not None:
            pattern = (
                "(?:曾|已|独立)?(?:创业|创办|创立)"
                if self.background_claim == "ENTREPRENEURSHIP"
                else "(?:已|从).*(?:转行|转型|跨行业)"
            )
            if not re.search(pattern, quotes) or re.search(
                "计划|希望|准备|打算", quotes
            ):
                raise ValueError("背景事实缺明确已发生原文")
        m = self.measurement
        if m is not None:
            if self.kind != "project" or m.project_id != self.fact_id:
                raise ValueError("测量必须属于同一项目")
            if m.value is not None and (
                not m.metric
                or not m.unit
                or m.metric not in quotes
                or m.unit not in quotes
                or format(m.value.normalize(), "f") not in quotes
            ):
                raise ValueError("项目指标缺精确原文")
            if m.role_level is not None and not re.search(
                {1: "参与", 2: "核心", 3: "主导|负责"}[m.role_level], quotes
            ):
                raise ValueError("项目角色缺精确原文")
            if m.managed_team_size is not None and not re.search(
                r"管理[^。\n]{0,20}" + str(m.managed_team_size) + r"\s*[人位]", quotes
            ):
                raise ValueError("管理人数不能用项目总人数代替")
        for value in (self.organization, self.title, self.degree, self.major):
            if value is not None and value not in quotes:
                raise ValueError("结构字段缺原文证据")
        for date_value in (self.start_date, self.end_date):
            if date_value is not None and date_value.source_text not in quotes:
                raise ValueError("日期缺原文证据")
        if self.ongoing is True and not any(
            word in quotes for word in ("至今", "现在", "Present", "present")
        ):
            raise ValueError("至今缺原文证据")
        if self.is_internship is True and not any(
            word in quotes.casefold() for word in ("实习", "intern")
        ):
            raise ValueError("实习缺原文证据")
        return self


class Requirement(HrModel):
    requirement_id: str = Field(min_length=1, max_length=100)
    criterion: str = Field(min_length=1, max_length=1000)


class Assessment(HrModel):
    requirement_id: str = Field(min_length=1, max_length=100)
    status: Literal[
        "STRONG", "MATCH", "PARTIAL", "EXPLICIT_NOT_MET", "UNKNOWN", "NEEDS_REVIEW"
    ]
    reason: str = Field(min_length=1, max_length=300)
    evidence: list[Evidence] = Field(max_length=5)

    @model_validator(mode="after")
    def evidence_required(self) -> "Assessment":
        if self.status not in ("UNKNOWN", "NEEDS_REVIEW") and not self.evidence:
            raise ValueError("已知判断必须有证据")
        return self


class FactOutput(HrModel):
    facts: list[Fact] = Field(max_length=500)


class EvaluationOutput(HrModel):
    assessments: list[Assessment] = Field(max_length=60)


class ExplanationItem(HrModel):
    text: str = Field(min_length=1, max_length=300)
    evidence: list[Evidence] = Field(min_length=1, max_length=5)
    requirement_ids: list[str] = Field(min_length=1, max_length=5)


class ExplanationOutput(HrModel):
    verification_points: list[ExplanationItem] = Field(
        default_factory=list, max_length=4
    )
    quality_notes: list[ExplanationItem] = Field(default_factory=list, max_length=3)
    summary: str = Field(default="", max_length=80)
    highlights: list[ExplanationItem] = Field(max_length=5)
    gaps: list[ExplanationItem] = Field(max_length=4)


class JdHardCondition(HrModel):
    type: Literal[
        "EDUCATION",
        "WORK_EXPERIENCE",
        "REQUIRED_SKILL",
        "CERTIFICATE",
        "LOCATION",
        "LANGUAGE",
        "PROJECT_SCALE",
        "TEAM_SIZE",
    ]
    values: list[str] = Field(default_factory=list, max_length=20)
    match_mode: Literal["ALL", "ANY"] = "ALL"
    threshold: Decimal | None = Field(default=None, gt=0, le=1000000000000)
    unit: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def required_value(self) -> "JdHardCondition":
        semantic = self.type in {
            "REQUIRED_SKILL",
            "CERTIFICATE",
            "LOCATION",
            "LANGUAGE",
        }
        if semantic and (
            not self.values or any(not v or len(v) > 200 for v in self.values)
        ):
            raise ValueError("硬条件缺少有界标准值")
        if not semantic and self.threshold is None:
            raise ValueError("数值硬条件缺少阈值")
        return self


class JdSkill(HrModel):
    name: str = Field(min_length=1, max_length=200)
    expected_level: int | None = Field(default=None, ge=1, le=5)
    importance: int = Field(default=5, ge=1, le=10)


class JdExperience(HrModel):
    minimum_months: int | None = Field(default=None, ge=1, le=1200)
    maximum_months: int | None = Field(default=None, ge=1, le=1200)
    industry: str | None = Field(default=None, max_length=200)
    function: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def ordered_range(self) -> "JdExperience":
        if (
            self.minimum_months
            and self.maximum_months
            and self.minimum_months > self.maximum_months
        ):
            raise ValueError("经验区间倒置")
        return self


class JdProject(HrModel):
    metric: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, max_length=100)
    expected_scale: Decimal | None = Field(default=None, gt=0, le=1000000000000)
    expected_role: int | None = Field(default=None, ge=1, le=3)
    managed_team_size: int | None = Field(default=None, ge=1, le=100000)


class JdCandidate(HrModel):
    type: Literal["HARD_CONDITION", "SKILL", "EXPERIENCE", "PROJECT"]
    dimension: Literal["SKILL", "EXPERIENCE", "PROJECT", "EDUCATION", "BONUS"]
    criterion: str = Field(min_length=1, max_length=1000)
    source_quote: str = Field(min_length=1, max_length=1000)
    default_adopted: Literal[False] = False
    hard_condition: JdHardCondition | None = None
    skill: JdSkill | None = None
    experience: JdExperience | None = None
    project: JdProject | None = None

    @model_validator(mode="after")
    def category_payload(self) -> "JdCandidate":
        key = {
            "HARD_CONDITION": "hard_condition",
            "SKILL": "skill",
            "EXPERIENCE": "experience",
            "PROJECT": "project",
        }[self.type]
        if getattr(self, key) is None or any(
            getattr(self, other) is not None
            for other in {"hard_condition", "skill", "experience", "project"} - {key}
        ):
            raise ValueError("JD候选必须具有且仅具有同类型结构")
        if self.type != "HARD_CONDITION" and self.dimension != self.type:
            raise ValueError("JD类型与维度不一致")
        return self


class JdOutput(HrModel):
    candidates: list[JdCandidate] = Field(max_length=60)


class InterviewOptions(HrModel):
    target_minutes: int = Field(default=60, ge=1, le=600)
    counts: tuple[int, int, int, int, int, int] | None = None
    durations: tuple[int, int, int, int, int, int] | None = None


class InterviewQuestion(HrModel):
    question_id: str = Field(min_length=1, max_length=100)
    layer: int = Field(ge=1, le=6)
    text: str = Field(min_length=1, max_length=1000)
    purpose: str = Field(min_length=1, max_length=300)
    answer_points: list[str] = Field(min_length=3, max_length=5)
    followups: list[str] = Field(min_length=2, max_length=3)
    excellent: str = Field(min_length=1, max_length=1000)
    qualified: str = Field(min_length=1, max_length=1000)
    needs_verification: str = Field(min_length=1, max_length=1000)
    source_ids: list[str] = Field(max_length=5)
    minutes: int = Field(ge=1, le=15)
    dimension: str = Field(min_length=1, max_length=100)


class InterviewOutput(HrModel):
    questions: list[InterviewQuestion] = Field(max_length=40)
    unfilled: list[int] = Field(default_factory=list, max_length=6)


class ExtractionInput(HrModel):
    archive_raw: bool = False
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(max_length=140000000)
    sha256: str = Field(pattern="^[a-f0-9]{64}$")


class TalentSearchOutput(HrModel):
    relevance: float = Field(ge=0, le=1)
    matches: list[Evidence] = Field(default_factory=list, max_length=5)


class HrWorkload(HrModel):
    run_ref: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^hr-(?:trial|import|batch|interview|search|match)-[A-Za-z0-9-]+$",
    )
    skill_key: Literal[
        "hr.requirements.evaluate",
        "hr.resume.structure",
        "hr.match.explain",
        "hr.interview.generate",
        "hr.talent.search",
    ] = "hr.requirements.evaluate"
    attempts: int = Field(default=3, ge=1, le=3)


class HrSkillRequest(HrModel):
    memory_context: MemoryContextInput = Field(default_factory=MemoryContextEnvelope)
    maximum_attempts: int = Field(default=3, ge=1, le=3)
    contract_version: Literal["hr-skill/1"] = "hr-skill/1"
    run_id: str = Field(min_length=1, max_length=100)
    operation_id: str = Field(min_length=1, max_length=100)
    candidate_ref: str = Field(default="", max_length=100)
    search_query: str = Field(default="", max_length=500)
    expected_bindings: dict[str, dict[str, str]] = Field(
        default_factory=dict, max_length=5
    )
    blocks: list[Block] = Field(default_factory=list, max_length=1000)
    requirements: list[Requirement] = Field(default_factory=list, max_length=60)
    facts: list[Fact] = Field(default_factory=list, max_length=500)
    assessments: list[Assessment] = Field(default_factory=list, max_length=60)
    jd_text: str = Field(default="", max_length=100000)
    interview: InterviewOptions = Field(default_factory=InterviewOptions)
    extraction: ExtractionInput | None = None
    workload: list[HrWorkload] = Field(default_factory=list, max_length=1700)
    workload_plan_ref: str | None = Field(
        default=None, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    workload_budget_ref: str | None = Field(default=None, min_length=1, max_length=256)


class IdentityValue(HrModel):
    value: str | None = None
    quality: int = Field(default=0, ge=0, le=100)
    evidence: list[Evidence] = Field(default_factory=list, max_length=5)
    conflict: bool = False


class Identity(HrModel):
    name: IdentityValue = Field(default_factory=IdentityValue)
    phones: list[IdentityValue] = Field(default_factory=list, max_length=20)
    emails: list[IdentityValue] = Field(default_factory=list, max_length=20)
    confirmation_required: bool = True


class ExtractionOutput(HrModel):
    blocks: list[Block]
    cleaned_blocks: list[Block]
    identity: Identity
    content_hash: str
    quality_policy_version: Literal["quality-policy/1"] = "quality-policy/1"

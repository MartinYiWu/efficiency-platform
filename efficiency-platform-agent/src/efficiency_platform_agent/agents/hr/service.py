"""已发布Prompt与标准Provider之间的HR受控业务执行。"""

import asyncio
import base64
import json
from collections.abc import Callable
from hashlib import sha256
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from efficiency_platform_agent.context.stages import stage_entry
from efficiency_platform_agent.contracts.hr import (
    Block,
    EvaluationOutput,
    ExplanationOutput,
    FactOutput,
    HrSkillRequest,
    InterviewOutput,
    JdOutput,
    Requirement,
    TalentSearchOutput,
)
from efficiency_platform_agent.core.context_dispatch import allow_context_repair
from efficiency_platform_agent.core.execution_control import RunControl, execution_scope
from efficiency_platform_agent.core.ports import ModelProvider
from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderMessage,
    ProviderRequest,
)
from efficiency_platform_agent.prompts.contracts import PromptValue
from efficiency_platform_agent.prompts.runtime import PromptAssembler

from .definition import SKILLS
from .evaluation import (
    criterion_key,
    semantic_batches,
    validate_assessments,
    validate_evidence,
)
from .extraction import (
    extract_archive,
    extract_archive_raw,
    extract_resume,
    model_safe_blocks,
)
from .facts import split_fact_blocks
from .interview import FORBIDDEN, interview_plan, validate_interview

T = TypeVar("T", bound=BaseModel)


class HrRunControlStore(Protocol):
    async def get(
        self, tenant_id: str, run_id: str, maximum_attempts: int = 3
    ) -> RunControl: ...
    async def cancel(self, tenant_id: str, run_id: str) -> None: ...


class HrSkillService:
    def __init__(
        self,
        assembler: PromptAssembler | None,
        provider: ModelProvider | None,
        *,
        ocr: Callable[[bytes], list[Block]] | None = None,
    ) -> None:
        self.assembler, self.provider, self.ocr = assembler, provider, ocr

    async def execute(
        self, skill: str, request: HrSkillRequest, control: RunControl
    ) -> dict[str, object]:
        control.check()
        data: dict[str, object]
        if skill not in SKILLS.values() or skill == "hr.run.cancel":
            raise ValueError("HR_CONFIG_SKILL_UNKNOWN")
        if skill == "hr.resume.extract":
            source = request.extraction
            if source is None:
                raise ValueError("HR_FILE_INPUT_REQUIRED")
            content = base64.b64decode(source.content_base64, validate=True)
            if source.archive_raw:
                data = {
                    "documents": await asyncio.to_thread(
                        extract_archive_raw,
                        content,
                        source.sha256,
                        extension="." + source.filename.rsplit(".", 1)[-1].lower(),
                    )
                }
            elif source.filename.lower().endswith((".zip", ".rar", ".7z")):
                data = {
                    "documents": await asyncio.to_thread(
                        extract_archive,
                        content,
                        source.sha256,
                        ocr=self.ocr,
                        extension="." + source.filename.rsplit(".", 1)[-1].lower(),
                    )
                }
            else:
                extracted = await asyncio.to_thread(
                    extract_resume,
                    source.filename,
                    content,
                    source.sha256,
                    ocr=self.ocr,
                )
                data = extracted.model_dump(mode="json")
        else:
            if self.assembler is None or self.provider is None:
                raise ValueError("HR_CONFIG_MODEL_OR_PROMPT_UNAVAILABLE")
            data = await self._execute_model_skill(skill, request, control)
        control.check()
        return {
            "contract_version": "hr-result/1",
            "skill": skill,
            "run_id": request.run_id,
            "operation_id": request.operation_id,
            "data": data,
        }

    async def _execute_model_skill(
        self, skill: str, request: HrSkillRequest, control: RunControl
    ) -> dict[str, object]:
        if request.expected_bindings:
            if self.assembler is None:
                raise ValueError("HR_CONFIG_PUBLISHED_ASSETS_NOT_READY")
            expected = request.expected_bindings.get(skill)
            current = await self.assembler.published_metadata(skill)
            if expected is None or expected != current:
                raise ValueError("HR_CONFIG_FROZEN_BINDING_CHANGED")
        if sum(len(b.text) for b in request.blocks) > 100000:
            raise ValueError("HR_FILE_TEXT_LIMIT")
        request = request.model_copy(
            update={
                "blocks": model_safe_blocks(request.blocks),
                "jd_text": model_safe_blocks(
                    [Block(block_id="jd", text=request.jd_text)]
                )[0].text,
            }
        )
        for fact in request.facts:
            validate_evidence(fact.evidence, request.blocks)
        if skill == "hr.requirements.evaluate":
            batches = semantic_batches(request.requirements)
            assessments = []
            for index, batch in enumerate(batches):
                sub = request.model_copy(update={"requirements": batch})

                def validate_batch(
                    out: EvaluationOutput, expected: list[Requirement] = batch
                ) -> None:
                    validate_assessments(expected, out.assessments, request.blocks)

                output = await self._generate(
                    skill,
                    sub,
                    EvaluationOutput,
                    control,
                    suffix=str(index),
                    validator=validate_batch,
                )
                assessments.extend(output.assessments)
            # 同一标准用于硬软要求时只判断一次，再按原始ID复用。
            canonical = {
                criterion_key(r.criterion): r.requirement_id
                for batch in batches
                for r in batch
            }
            by_id = {a.requirement_id: a for a in assessments}
            result = [
                by_id[canonical[criterion_key(r.criterion)]].model_copy(
                    update={"requirement_id": r.requirement_id}
                )
                for r in request.requirements
            ]
            validate_assessments(request.requirements, result, request.blocks)
            return EvaluationOutput(assessments=result).model_dump(mode="json")
        if skill == "hr.resume.structure":

            def facts_valid(out: FactOutput) -> None:
                if len({f.fact_id for f in out.facts}) != len(out.facts):
                    raise ValueError("HR_FACT_DUPLICATE_ID")
                for fact in out.facts:
                    validate_evidence(fact.evidence, request.blocks)
                    if any(w in fact.value for w in FORBIDDEN):
                        raise ValueError("HR_FACT_FORBIDDEN_ATTRIBUTE")
                for kind, limit in (
                    ("employment", 100),
                    ("project", 100),
                    ("skill", 200),
                ):
                    if sum(f.kind == kind for f in out.facts) > limit:
                        raise ValueError("HR_FACT_COUNT_EXCEEDED")

            chunks, mapping = split_fact_blocks(request.blocks)
            if len(chunks) > 12 or len(chunks) * 3 > 60 - control.calls:
                raise ValueError("HR_EVALUATION_WORK_LIMIT_EXCEEDED")
            facts = []
            for index, chunk in enumerate(chunks):

                def piece_valid(out: FactOutput, current: list[Block] = chunk) -> None:
                    for fact in out.facts:
                        validate_evidence(fact.evidence, current)

                extracted = await self._generate(
                    skill,
                    request.model_copy(update={"blocks": chunk, "facts": []}),
                    FactOutput,
                    control,
                    suffix=str(index),
                    validator=piece_valid,
                )
                for fact in extracted.facts:
                    evidence = []
                    for item in fact.evidence:
                        original, start = mapping[item.block_id]
                        evidence.append(
                            item.model_copy(
                                update={
                                    "block_id": original,
                                    "start": item.start + start,
                                    "end": item.end + start,
                                }
                            )
                        )
                    facts.append(fact.model_copy(update={"evidence": evidence}))
            merged = FactOutput(facts=facts)
            facts_valid(merged)
            return merged.model_dump(mode="json")
        elif skill == "hr.match.explain":
            if not request.assessments:
                raise ValueError("HR_EVALUATION_ASSESSMENTS_REQUIRED")
            validate_assessments(
                request.requirements, request.assessments, request.blocks
            )
            assessed = {item.requirement_id: item for item in request.assessments}

            def explanation_valid(out: ExplanationOutput) -> None:
                if any(word in out.summary for word in FORBIDDEN):
                    raise ValueError("HR_EVALUATION_PROTECTED_ATTRIBUTE")
                for item in (
                    out.highlights
                    + out.gaps
                    + out.verification_points
                    + out.quality_notes
                ):
                    if any(word in item.text for word in FORBIDDEN):
                        raise ValueError("HR_EVALUATION_PROTECTED_ATTRIBUTE")
                    validate_evidence(item.evidence, request.blocks)
                    if not set(item.requirement_ids) <= assessed.keys():
                        raise ValueError("HR_EVALUATION_EXPLANATION_SOURCE_INVALID")
                    allowed = {
                        e.model_dump_json()
                        for reference in item.requirement_ids
                        for e in assessed[reference].evidence
                    }
                    if any(e.model_dump_json() not in allowed for e in item.evidence):
                        raise ValueError("HR_EVALUATION_EXPLANATION_EVIDENCE_INVALID")
                summary_sources = [
                    a.reason for a in request.assessments if a.evidence
                ] + [e.quote for a in request.assessments for e in a.evidence]
                if out.summary and not any(
                    out.summary in value for value in summary_sources
                ):
                    raise ValueError("HR_EVALUATION_EXPLANATION_SUMMARY_UNGROUNDED")
                for item in out.highlights:
                    if any(
                        assessed[reference].status not in ("STRONG", "MATCH")
                        for reference in item.requirement_ids
                    ):
                        raise ValueError("HR_EVALUATION_EXPLANATION_STATUS_INVALID")

            explanation = await self._generate(
                skill, request, ExplanationOutput, control, validator=explanation_valid
            )
            return explanation.model_dump(mode="json")
        elif skill == "hr.talent.search":
            from .talent import validate_search

            search_result = await self._generate(
                skill,
                request,
                TalentSearchOutput,
                control,
                validator=lambda out: validate_search(out, request),
            )
            return search_result.model_dump(mode="json")
        elif skill == "hr.interview.generate":
            interview_plan(
                request.interview.target_minutes,
                request.interview.counts,
                request.interview.durations,
            )
            interview = await self._generate(
                skill,
                request,
                InterviewOutput,
                control,
                validator=lambda out: validate_interview(out, request),
            )
            return interview.model_dump(mode="json")
        else:

            def jd_valid(out: JdOutput) -> None:
                for item in out.candidates:
                    if item.source_quote not in request.jd_text or any(
                        w in (item.criterion + item.source_quote) for w in FORBIDDEN
                    ):
                        raise ValueError("HR_JD_SOURCE_OR_ATTRIBUTE_INVALID")

            jd = await self._generate(
                skill, request, JdOutput, control, validator=jd_valid
            )
            return jd.model_dump(mode="json")

    @stage_entry(
        "hr",
        inputs=("skill", "request"),
        identity=("skill", "request.operation_id", "suffix"),
        node_fields=("skill",),
    )
    async def _generate(
        self,
        skill: str,
        request: HrSkillRequest,
        output_type: type[T],
        control: RunControl,
        *,
        suffix: str = "0",
        validator: Callable[[T], None],
    ) -> T:
        assert self.assembler is not None and self.provider is not None
        provider = self.provider
        # 身份字段不在模型请求契约内；外部简历仅作为不可信JSON变量。
        logical_payload = request.model_dump(
            mode="json", exclude={"extraction", "memory_context"}
        )
        payload = request.model_dump(
            mode="json",
            exclude={
                "memory_context",
                "extraction",
                "workload",
                "workload_budget_ref",
                "workload_plan_ref",
                "maximum_attempts",
                "expected_bindings",
                "run_id",
                "operation_id",
                "contract_version",
            },
        )
        if skill == "hr.talent.search":
            payload = {
                "search_query": request.search_query,
                "blocks": [block.model_dump(mode="json") for block in request.blocks],
            }
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(serialized.encode()) > 48 * 1024:
            raise ValueError("HR_EVALUATION_INPUT_TOO_LARGE")
        stage = f"{skill}:{request.operation_id}:{suffix}"
        input_key = f"hr-input:{stage}"
        digest = sha256(
            json.dumps(
                logical_payload, ensure_ascii=False, separators=(",", ":")
            ).encode()
        ).hexdigest()
        if input_key in control.results and control.results[input_key] != digest:
            raise ValueError("HR_EVALUATION_OPERATION_INPUT_CONFLICT")
        control.results[input_key] = digest
        assembled = await self.assembler.assemble(
            run_id=request.run_id,
            stage=stage,
            prompt_key=skill,
            variables={"input_json": PromptValue(payload, "user_input")},
        )
        policy = assembled.model_policy
        if (
            policy.max_input_tokens < 131072
            or not 1 <= policy.max_output_tokens <= 4096
            or policy.max_retries > 2
        ):
            raise ValueError("HR_CONFIG_MODEL_POLICY_INVALID")
        if (
            dict(assembled.output_contract.json_schema)
            != output_type.model_json_schema()
        ):
            raise ValueError("HR_CONFIG_OUTPUT_CONTRACT_MISMATCH")
        messages = tuple(
            ProviderMessage(m.role.lower(), m.content) for m in assembled.messages
        ) + (
            ProviderMessage(
                "developer",
                "只返回符合已发布输出契约的JSON对象："
                + json.dumps(
                    output_type.model_json_schema(),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            ),
        )
        options = JsonObject(
            (
                ("logical_model", policy.model_name),
                ("temperature", policy.temperature),
                ("max_tokens", policy.max_output_tokens),
                ("response_format", JsonObject((("type", "json_object"),))),
            )
        )
        if (
            sum(len(str(m.content).encode()) for m in messages)
            + len(output_type.model_json_schema().__str__().encode())
            > 60 * 1024
        ):
            raise ValueError("HR_EVALUATION_INPUT_TOO_LARGE")

        effective_attempts = min(
            3,
            getattr(control, "maximum_attempts", request.maximum_attempts),
            policy.max_retries + 1,
        )

        async def invoke() -> T:
            for attempt in range(effective_attempts):
                control.check()
                attempt_messages = messages
                if attempt:
                    attempt_messages += (
                        ProviderMessage(
                            "developer",
                            "前次输出未通过结构或证据契约。只返回完整合法JSON，引用必须逐字匹配输入块，禁止补写事实；缺失证据使用UNKNOWN或标记题槽不足。",
                        ),
                    )
                body = {
                    "messages": [
                        {"role": m.role, "content": m.content} for m in attempt_messages
                    ],
                    "model": policy.model_name,
                    "max_tokens": policy.max_output_tokens,
                    "response_format": {"type": "json_object"},
                }
                if (
                    len(
                        json.dumps(
                            body, ensure_ascii=False, separators=(",", ":")
                        ).encode()
                    )
                    > 60 * 1024
                ):
                    raise ValueError("HR_EVALUATION_INPUT_TOO_LARGE")
                with execution_scope(control):
                    result = await provider.complete(
                        ProviderRequest(
                            "provider-request/1",
                            attempt_messages,
                            options,
                            min(policy.read_timeout_ms, 600000),
                        )
                    )
                if result.error:
                    raise ValueError(result.error.code)
                try:
                    if result.message is None or not isinstance(
                        result.message.content, str
                    ):
                        raise ValueError("HR_EVALUATION_CONTRACT_FAILED")
                    value = output_type.model_validate_json(result.message.content)
                    validator(value)
                    return value
                except (ValueError, ValidationError):
                    if attempt + 1 >= effective_attempts:
                        raise ValueError("HR_EVALUATION_CONTRACT_FAILED") from None
                    await allow_context_repair()
            raise AssertionError("不可达")

        return await control.execute(stage, invoke)

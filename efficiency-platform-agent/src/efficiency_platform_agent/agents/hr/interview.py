"""面试六层题量与安全来源校验。"""

from efficiency_platform_agent.contracts.hr import HrSkillRequest, InterviewOutput

PRESETS = {
    30: (2, 2, 1, 2, 1, 1),
    45: (3, 2, 2, 3, 2, 1),
    60: (4, 3, 2, 4, 3, 1),
    90: (6, 5, 3, 6, 4, 2),
}
DURATIONS = (3, 3, 3, 4, 4, 3)
FORBIDDEN = (
    "婚姻",
    "婚育",
    "生育",
    "怀孕",
    "民族",
    "宗教",
    "政治面貌",
    "身份证",
    "性取向",
    "健康状况",
    "年龄",
    "性别",
    "户籍",
    "照片",
    "残疾",
    "出生日期",
    "出生",
    "生日",
    "籍贯",
    "血型",
    "星座",
    "身高",
    "体重",
    "院校声望",
    "性格",
    "忠诚度",
    "离职风险",
    "候选人稳定性",
    "AI认为",
    "评分低",
    "需警惕",
)


def interview_plan(
    target: int,
    counts: tuple[int, ...] | None = None,
    durations: tuple[int, ...] | None = None,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    selected = counts if counts is not None else PRESETS.get(target)
    timing = durations or DURATIONS
    if (
        selected is None
        or len(selected) != 6
        or any(n < 0 or n > 10 for n in selected)
        or not 1 <= sum(selected) <= 40
    ):
        raise ValueError("HR_INTERVIEW_COUNT_INVALID")
    if (
        len(timing) != 6
        or any(n < 1 or n > 15 for n in timing)
        or sum(n * t for n, t in zip(selected, timing, strict=True)) > target
    ):
        raise ValueError("HR_INTERVIEW_DURATION_INVALID")
    return selected, timing


def validate_interview(output: InterviewOutput, request: HrSkillRequest) -> None:
    counts, timing = interview_plan(
        request.interview.target_minutes,
        request.interview.counts,
        request.interview.durations,
    )
    known = {f.fact_id for f in request.facts} | {
        r.requirement_id for r in request.requirements
    }
    if len({q.question_id for q in output.questions}) != len(output.questions):
        raise ValueError("HR_INTERVIEW_DUPLICATE_QUESTION")
    if any(word in output.model_dump_json() for word in FORBIDDEN):
        raise ValueError("HR_INTERVIEW_FORBIDDEN_CONTENT")
    for layer in range(1, 7):
        questions = [q for q in output.questions if q.layer == layer]
        if len(questions) > counts[layer - 1] or (
            len(questions) < counts[layer - 1] and layer not in output.unfilled
        ):
            raise ValueError("HR_INTERVIEW_COVERAGE_INVALID")
        for q in questions:
            if (
                q.minutes != timing[layer - 1]
                or not set(q.source_ids) <= known
                or (layer <= 3 and not q.source_ids)
            ):
                raise ValueError("HR_INTERVIEW_SOURCE_INVALID")

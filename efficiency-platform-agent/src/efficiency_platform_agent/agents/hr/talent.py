"""人才检索相关度不是能力分；每个命中必须引用真实清洗块。"""

from efficiency_platform_agent.contracts.hr import HrSkillRequest, TalentSearchOutput

from .evaluation import validate_evidence


def validate_search(output: TalentSearchOutput, request: HrSkillRequest) -> None:
    if not request.search_query.strip() or not request.blocks:
        raise ValueError("HR_SEARCH_INPUT_REQUIRED")
    validate_evidence(output.matches, request.blocks)
    if output.relevance > 0 and not output.matches:
        raise ValueError("HR_SEARCH_EVIDENCE_REQUIRED")

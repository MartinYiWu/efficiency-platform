"""字段候选的确定性分类；不选最新值、不写入权威记忆。"""

from dataclasses import dataclass, field
from typing import Literal

from efficiency_platform_agent.core.memory import require_count, require_id

type ProposalAction = Literal["ADD", "REPLACE_CANDIDATE", "CONFLICT_CANDIDATE", "NOOP"]


@dataclass(frozen=True, slots=True)
class CurrentFieldValue:
    item_id: str
    version_id: str
    kind: str
    field_key: str
    value: str = field(repr=False)
    revision: int

    def __post_init__(self) -> None:
        for value in (self.item_id, self.version_id, self.kind, self.field_key):
            require_id(value)
        require_count(self.revision)
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("PROPOSAL_CURRENT_VALUE_INVALID")


def classify_field(
    value: str,
    current: tuple[CurrentFieldValue, ...],
    competing_values: frozenset[str],
    replacement_item_ids: frozenset[str],
) -> ProposalAction:
    values = {item.value for item in current}
    if len(values) > 1 or competing_values - {value}:
        return "CONFLICT_CANDIDATE"
    if values == {value}:
        return "NOOP"
    if not current:
        return "ADD"
    if len(current) == 1 and current[0].item_id in replacement_item_ids:
        return "REPLACE_CANDIDATE"
    return "CONFLICT_CANDIDATE"

"""供后续 S2 接受测试复用的确定性时钟与 ID Fake。"""

from efficiency_platform_agent.persistence.in_memory import (
    FixedClock,
    SequenceIdGenerator,
)

__all__ = ["FixedClock", "SequenceIdGenerator"]

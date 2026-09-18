"""结构化成品组装与格式质量检查。"""

from .deliverable_v2 import (
    DeliveryPresentationValidator,
    assemble_set_v2,
    project_set_v2_to_v1,
    render_copy_text,
)

__all__ = [
    "DeliveryPresentationValidator",
    "assemble_set_v2",
    "project_set_v2_to_v1",
    "render_copy_text",
]

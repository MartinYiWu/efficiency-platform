"""从结构化模型流中释放完整、顺序稳定且引用有效的回答块。"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from .citations import CitationGuardError, validate_citation_closure
from .renderer import answer_deltas, render_answer
from .state import (
    AnswerMode,
    CompanyParagraph,
    CustomerServiceAnswer,
    Evidence,
    EvidencePack,
)


@dataclass
class _Container:
    value: dict[str, Any] | list[Any]
    path: tuple[str | int, ...]
    phase: str
    key: str | None = None


class AnswerSectionStream:
    def __init__(
        self,
        evidence: tuple[Evidence, ...] | EvidencePack,
        emit: Callable[[str], None],
        *,
        expected_mode: AnswerMode | None = None,
    ) -> None:
        entries = evidence if isinstance(evidence, tuple) else evidence.entries
        self.allowed = {entry.chunk_id for entry in entries}
        self.evidence = evidence
        self.emit = emit
        self.expected_mode = expected_mode
        self._content = ""
        self._cursor = 0
        self._stack: list[_Container] = []
        self._root: dict[str, Any] | None = None
        self._closed: set[tuple[str | int, ...]] = set()
        self._emitted: list[str] = []
        self._decoder = json.JSONDecoder()

    def feed(self, content: str) -> None:
        if not content.startswith(self._content):
            raise ValueError("流式模型内容不能改写已接收的前缀")
        self._content = content
        while self._cursor < len(content):
            char = content[self._cursor]
            if char.isspace():
                self._cursor += 1
                continue
            if not self._stack:
                if self._root is not None or char != "{":
                    raise ValueError("流式回答必须为单个 JSON 对象")
                self._root = {}
                self._stack.append(_Container(self._root, (), "key_or_end"))
                self._cursor += 1
                continue
            frame = self._stack[-1]
            if char in "}]" and frame.phase in {"key_or_end", "value_or_end", "comma"}:
                if (char == "}") != isinstance(frame.value, dict):
                    raise ValueError("流式 JSON 容器不匹配")
                self._closed.add(frame.path)
                self._stack.pop()
                self._cursor += 1
                self._release()
                continue
            if frame.phase == "comma":
                if char != ",":
                    raise ValueError("流式 JSON 缺少分隔符")
                frame.phase = "key" if isinstance(frame.value, dict) else "value"
                self._cursor += 1
                continue
            if frame.phase == "colon":
                if char != ":":
                    raise ValueError("流式 JSON 字段缺少冒号")
                frame.phase = "value"
                self._cursor += 1
                continue
            if frame.phase in {"key", "key_or_end"}:
                if char != '"':
                    raise ValueError("流式 JSON 字段名无效")
                token = self._decode()
                if token is None:
                    return
                key, self._cursor = token
                if key in frame.value:
                    raise ValueError("流式 JSON 包含重复字段")
                frame.key = key
                frame.phase = "colon"
                continue
            if frame.phase not in {"value", "value_or_end"}:
                raise ValueError("流式 JSON 状态无效")
            if isinstance(frame.value, dict):
                if frame.key is None:
                    raise ValueError("流式 JSON 缺少字段名")
                segment: str | int = frame.key
            else:
                segment = len(frame.value)
            path = frame.path + (segment,)
            if char in "[{":
                child: dict[str, Any] | list[Any] = {} if char == "{" else []
                self._attach(frame, child)
                self._stack.append(
                    _Container(
                        child, path, "key_or_end" if char == "{" else "value_or_end"
                    )
                )
                self._cursor += 1
                continue
            token = self._decode()
            if token is None:
                return
            value, end = token
            if not isinstance(value, str) and end == len(content):
                return
            self._cursor = end
            self._attach(frame, value)
            self._closed.add(path)
            self._release()

    def _decode(self) -> tuple[Any, int] | None:
        try:
            return self._decoder.raw_decode(self._content, self._cursor)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _attach(frame: _Container, value: Any) -> None:
        if isinstance(frame.value, dict):
            if frame.key is None:
                raise ValueError("流式 JSON 缺少字段名")
            frame.value[frame.key] = value
        else:
            frame.value.append(value)
        frame.phase = "comma"

    def _release(self) -> None:
        root = self._root
        if root is None:
            return
        if self.expected_mode is not None:
            if "answer_mode" in root and root["answer_mode"] != self.expected_mode:
                raise ValueError("流式回答模式与决策不一致")
            if (
                "contract_version" in root
                and root["contract_version"] != "customer-service-answer/1"
            ):
                raise ValueError("流式回答契约版本无效")
            if not {("answer_mode",), ("contract_version",)}.issubset(self._closed):
                return
        if (
            self.expected_mode is not None
            and ("knowledge_gap",) not in self._closed
            and () not in self._closed
        ):
            return
        blocks: list[str] = []
        gap = root.get("knowledge_gap")
        if gap is not None:
            if not isinstance(gap, str):
                raise ValueError("资料缺口必须为字符串或 null")
            if gap:
                blocks.append(gap)
        numbers: dict[UUID, int] = {}
        sections = root.get("company_sections", [])
        if not isinstance(sections, list):
            raise ValueError("公司回答必须为段落数组")  # noqa: TRY004 - 模型 JSON 契约错误
        for section_index, section in enumerate(sections):
            if not isinstance(section, dict):
                raise ValueError("公司回答区块无效")  # noqa: TRY004 - 模型 JSON 契约错误
            title = section.get("title")
            paragraphs = section.get("paragraphs", [])
            if not isinstance(paragraphs, list):
                raise ValueError("公司回答段落无效")  # noqa: TRY004 - 模型 JSON 契约错误
            header_added = False
            for paragraph_index, value in enumerate(paragraphs):
                path = (
                    "company_sections",
                    section_index,
                    "paragraphs",
                    paragraph_index,
                )
                if path not in self._closed or not isinstance(title, str):
                    self._emit_prefix(blocks)
                    return
                paragraph = CompanyParagraph.model_validate(value)
                if not set(paragraph.supporting_chunk_ids).issubset(self.allowed):
                    raise CitationGuardError("流式段落包含证据之外的引用")
                if not header_added:
                    blocks.append(f"## {title}")
                    header_added = True
                suffix = ""
                for chunk_id in paragraph.supporting_chunk_ids:
                    if chunk_id not in numbers:
                        numbers[chunk_id] = len(numbers) + 1
                    suffix += f"[{numbers[chunk_id]}]"
                blocks.append(f"{paragraph.text}{suffix}")
        company_complete = ("company_sections",) in self._closed or () in self._closed
        if not company_complete:
            self._emit_prefix(blocks)
            return
        general = root.get("general_advice")
        if general is not None:
            if not isinstance(general, dict):
                raise ValueError("通用建议区块无效")
            title = general.get("title")
            if title is not None and title != "通用建议，非公司制度":
                raise ValueError("通用建议标题无效")
            paragraphs = general.get("paragraphs", [])
            if not isinstance(paragraphs, list):
                raise ValueError("通用建议必须为字符串数组")
            if title is not None and paragraphs:
                if not all(isinstance(item, str) for item in paragraphs):
                    raise ValueError("通用建议段落必须为字符串")
                blocks.append(f"## {title}")
                blocks.extend(paragraphs)
        self._emit_prefix(blocks)

    def _emit_prefix(self, blocks: list[str]) -> None:
        blocks = list(filter(None, blocks))
        if blocks[: len(self._emitted)] != self._emitted:
            raise ValueError("流式回答块顺序或内容发生变化")
        for block in blocks[len(self._emitted) :]:
            self.emit(block)
            self._emitted.append(block)

    def finish(self, answer: CustomerServiceAnswer) -> None:
        if self._stack or () not in self._closed:
            raise ValueError("流式回答 JSON 未完整结束")
        parsed = CustomerServiceAnswer.model_validate_json(self._content)
        if parsed != answer:
            raise ValueError("模型最终答案与流式内容不一致")
        validate_citation_closure(answer, self.evidence)
        blocks = answer_deltas(render_answer(answer, self.evidence))
        if tuple(self._emitted) != blocks[: len(self._emitted)]:
            raise ValueError("流式回答与最终渲染前缀不一致")


__all__ = ["AnswerSectionStream"]

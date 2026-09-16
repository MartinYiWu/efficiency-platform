"""运营证据包的离线结构与证据关联校验。

本模块只校验已经传入的字段，不访问 URL、不调用搜索服务，也不宣称已经核验网页原文。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

from .task import SourceScope

_STABLE_ID = re.compile(r"[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?")


class EvidenceDuplicateStatus(StrEnum):
    """同一规范 URL 在证据包中的出现次序。"""

    UNIQUE = "unique"
    DUPLICATE = "duplicate"


class EvidenceQualityStatus(StrEnum):
    """离线证据字段质量状态，不代表事实真实性。"""

    VALID = "valid"
    INVALID = "invalid"
    UNVERIFIED = "unverified"
    ACCEPTED = "valid"
    REJECTED = "invalid"


@dataclass(frozen=True, slots=True)
class TimeWindow:
    """可选的非负时间范围；端点为空表示开放边界。"""

    starts_at_epoch_ms: int | None
    ends_at_epoch_ms: int | None

    def __post_init__(self) -> None:
        _non_negative_optional("starts_at_epoch_ms", self.starts_at_epoch_ms)
        _non_negative_optional("ends_at_epoch_ms", self.ends_at_epoch_ms)
        if (
            self.starts_at_epoch_ms is not None
            and self.ends_at_epoch_ms is not None
            and self.starts_at_epoch_ms > self.ends_at_epoch_ms
        ):
            raise ValueError("时间窗起点不能晚于终点")


def _stable_id(name: str, value: str) -> None:
    if not isinstance(value, str) or _STABLE_ID.fullmatch(value) is None:
        raise ValueError(f"{name}必须是稳定的小写标识")


def _text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}不能为空")


def _non_negative_optional(name: str, value: int | None) -> None:
    if value is not None and (
        not isinstance(value, int) or isinstance(value, bool) or value < 0
    ):
        raise ValueError(f"{name}必须是非负整数或空值")


def normalize_evidence_url(source_url: str) -> str:
    """规范化 HTTPS URL；该函数不发起网络请求。"""

    _text("source_url", source_url)
    parsed = urlsplit(source_url)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise ValueError("证据 URL 必须是 HTTPS 地址")
    # 计划只要求移除末尾一个斜杠，避免把不同路径静默合并。
    return source_url.removesuffix("/")


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """一条带来源、时间窗和结论关联的事实性证据。"""

    evidence_id: str
    title: str
    publisher: str
    source_url: str
    published_at_epoch_ms: int | None
    retrieved_at_epoch_ms: int
    source_scope: SourceScope
    supported_conclusion_ids: frozenset[str]
    within_time_window: bool
    duplicate_status: EvidenceDuplicateStatus
    quality_status: EvidenceQualityStatus

    def __post_init__(self) -> None:
        _stable_id("evidence_id", self.evidence_id)
        _text("title", self.title)
        _text("publisher", self.publisher)
        normalize_evidence_url(self.source_url)
        _non_negative_optional("published_at_epoch_ms", self.published_at_epoch_ms)
        if (
            not isinstance(self.retrieved_at_epoch_ms, int)
            or isinstance(self.retrieved_at_epoch_ms, bool)
            or self.retrieved_at_epoch_ms < 0
        ):
            raise ValueError("retrieved_at_epoch_ms必须是非负整数")
        if not isinstance(self.source_scope, SourceScope):
            raise TypeError("source_scope必须是SourceScope")
        if (
            not isinstance(self.supported_conclusion_ids, frozenset)
            or not self.supported_conclusion_ids
        ):
            raise ValueError("supported_conclusion_ids必须是非空不可变集合")
        for conclusion_id in self.supported_conclusion_ids:
            _stable_id("supported_conclusion_ids", conclusion_id)
        if not isinstance(self.within_time_window, bool):
            raise TypeError("within_time_window必须是布尔值")
        if not isinstance(self.duplicate_status, EvidenceDuplicateStatus):
            raise TypeError("duplicate_status必须是EvidenceDuplicateStatus")
        if not isinstance(self.quality_status, EvidenceQualityStatus):
            raise TypeError("quality_status必须是EvidenceQualityStatus")


@dataclass(frozen=True, slots=True)
class ConclusionSupport:
    """结论到证据 ID 的显式关联。"""

    conclusion_id: str
    evidence_ids: frozenset[str]

    def __post_init__(self) -> None:
        _stable_id("conclusion_id", self.conclusion_id)
        if not isinstance(self.evidence_ids, frozenset) or not self.evidence_ids:
            raise ValueError("evidence_ids必须是非空不可变集合")
        for evidence_id in self.evidence_ids:
            _stable_id("evidence_ids", evidence_id)


@dataclass(frozen=True, slots=True)
class EvidencePack:
    """版本化证据集合；只保存声明性记录，不持有网页正文。"""

    contract_version: str
    pack_id: str
    task_id: str
    records: tuple[EvidenceRecord, ...]
    supports: tuple[ConclusionSupport, ...]

    def __post_init__(self) -> None:
        if self.contract_version != "evidence-pack/1":
            raise ValueError("contract_version必须为evidence-pack/1")
        _stable_id("pack_id", self.pack_id)
        _stable_id("task_id", self.task_id)
        if not isinstance(self.records, tuple) or not isinstance(self.supports, tuple):
            raise TypeError("records和supports必须是不可变元组")
        if any(not isinstance(record, EvidenceRecord) for record in self.records):
            raise TypeError("records只能包含EvidenceRecord")
        if any(not isinstance(support, ConclusionSupport) for support in self.supports):
            raise TypeError("supports只能包含ConclusionSupport")


@dataclass(frozen=True, slots=True)
class EvidenceValidationResult:
    """四项离线检查结果，不等于网页原文或互联网事实核验。"""

    contract_version: str
    pack_id: str
    fields_complete: bool
    conclusions_linked: bool
    duplicates_consistent: bool
    time_window_valid: bool

    @property
    def is_valid(self) -> bool:
        """返回四项离线检查是否全部通过。"""

        return all(
            (
                self.fields_complete,
                self.conclusions_linked,
                self.duplicates_consistent,
                self.time_window_valid,
            )
        )

    @property
    def duplicate_status_valid(self) -> bool:
        """兼容调用方对重复状态检查的命名。"""

        return self.duplicates_consistent


def _validate_evidence_fields(pack: EvidencePack) -> None:
    for record in pack.records:
        normalize_evidence_url(record.source_url)
        if (
            not record.title.strip()
            or not record.publisher.strip()
            or not record.supported_conclusion_ids
        ):
            raise ValueError("证据字段不完整")


def _validate_conclusion_links(pack: EvidencePack) -> None:
    records_by_id = {record.evidence_id: record for record in pack.records}
    if len(records_by_id) != len(pack.records):
        raise ValueError("evidence_id不能重复")
    supports_by_id: dict[str, ConclusionSupport] = {}
    for support in pack.supports:
        if support.conclusion_id in supports_by_id:
            raise ValueError("conclusion_id不能重复")
        supports_by_id[support.conclusion_id] = support
        if any(
            evidence_id not in records_by_id for evidence_id in support.evidence_ids
        ):
            raise ValueError("结论引用了不存在的证据")
    for record in pack.records:
        if any(
            conclusion_id not in supports_by_id
            for conclusion_id in record.supported_conclusion_ids
        ):
            raise ValueError("证据关联了未声明的结论")
    for support in pack.supports:
        for evidence_id in support.evidence_ids:
            if (
                support.conclusion_id
                not in records_by_id[evidence_id].supported_conclusion_ids
            ):
                raise ValueError("结论与证据的双向关联不一致")


def _validate_duplicates(pack: EvidencePack) -> None:
    groups: dict[str, list[EvidenceRecord]] = {}
    for record in pack.records:
        groups.setdefault(normalize_evidence_url(record.source_url), []).append(record)
    for records in groups.values():
        for index, record in enumerate(records):
            expected = (
                EvidenceDuplicateStatus.UNIQUE
                if index == 0
                else EvidenceDuplicateStatus.DUPLICATE
            )
            if record.duplicate_status is not expected:
                raise ValueError("重复状态与规范 URL 分组不一致")


def _validate_time_windows(pack: EvidencePack) -> None:
    for record in pack.records:
        if (
            record.published_at_epoch_ms is not None
            and record.published_at_epoch_ms > record.retrieved_at_epoch_ms
        ):
            raise ValueError("发布时间不能晚于检索时间")
        if not record.within_time_window:
            raise ValueError("证据不在请求时间窗内")


def validate_evidence_pack(pack: EvidencePack) -> EvidenceValidationResult:
    """执行字段、结论、重复和时间窗四项离线校验，不访问任何外部资源。"""

    if not isinstance(pack, EvidencePack):
        raise TypeError("pack必须是EvidencePack")
    _validate_evidence_fields(pack)
    _validate_duplicates(pack)
    _validate_conclusion_links(pack)
    _validate_time_windows(pack)
    return EvidenceValidationResult(
        contract_version="evidence-validation/1",
        pack_id=pack.pack_id,
        fields_complete=True,
        conclusions_linked=True,
        duplicates_consistent=True,
        time_window_valid=True,
    )


__all__ = [name for name in globals() if not name.startswith("_")]

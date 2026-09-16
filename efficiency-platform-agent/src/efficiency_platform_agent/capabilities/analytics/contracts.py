"""Analytics 文件读取的稳定端口和受控数据对象。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from efficiency_platform_agent.core.run import JsonObject, JsonValue


class AnalyticsFileFormat(StrEnum):
    """允许声明的分析文件格式。"""

    CSV = "csv"
    JSON = "json"
    PARQUET = "parquet"
    XLSX = "xlsx"


@dataclass(frozen=True, slots=True)
class AnalyticsColumn:
    """分析列的稳定名称和标量类型。"""

    name: str
    value_type: str

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.value_type.strip():
            raise ValueError("分析列名称和类型不能为空")


@dataclass(frozen=True, slots=True)
class AnalyticsDatasetReference:
    """跨 Specialist 边界传递的分析数据引用。"""

    contract_version: str
    dataset_id: str
    tenant_id: str
    format: AnalyticsFileFormat
    source_reference: str
    schema_version: str

    def __post_init__(self) -> None:
        if self.contract_version != "analytics-dataset-reference/1":
            raise ValueError("分析数据引用版本不受支持")
        if not isinstance(self.format, AnalyticsFileFormat):
            raise TypeError("分析数据格式必须是AnalyticsFileFormat")
        for name, value in (
            ("dataset_id", self.dataset_id),
            ("tenant_id", self.tenant_id),
            ("schema_version", self.schema_version),
        ):
            if not value.strip():
                raise ValueError(f"{name}不能为空")
        if not self.source_reference.strip():
            raise ValueError("分析数据源引用不能为空")


@dataclass(frozen=True, slots=True)
class AnalyticsSummary:
    """可跨边界传递的有界分析摘要，不包含原始行。"""

    contract_version: str
    dataset_id: str
    tenant_id: str
    columns: tuple[AnalyticsColumn, ...]
    row_count: int
    aggregates: JsonObject
    truncated: bool
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.contract_version != "analytics-summary/1":
            raise ValueError("分析摘要版本不受支持")
        if self.row_count < 0:
            raise ValueError("分析摘要行数不能为负数")
        if not isinstance(self.columns, tuple) or not isinstance(self.warnings, tuple):
            raise TypeError("分析摘要集合必须使用 tuple")
        for key, value in self.aggregates.items:
            if not isinstance(key, str) or not key.strip():
                raise ValueError("分析指标 ID 不能为空")
            if isinstance(value, (tuple, JsonObject)):
                raise TypeError("分析摘要指标只能是有界标量")


@dataclass(frozen=True, slots=True)
class AnalyticsFileReadRequest:
    """一次受限文件读取请求。"""

    dataset_reference: AnalyticsDatasetReference
    sheet_name: str | None
    expected_columns: tuple[str, ...]
    max_rows: int
    max_columns: int
    max_bytes: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.expected_columns, tuple)
            or not self.expected_columns
            or any(
                not isinstance(item, str) or not item.strip()
                for item in self.expected_columns
            )
        ):
            raise ValueError("必须声明期望列")
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in (self.max_rows, self.max_columns, self.max_bytes)
        ):
            raise ValueError("文件读取上限必须为正数")


@dataclass(frozen=True, slots=True)
class AnalyticsDataset:
    """仅在 lease 生命周期内可见的不可变数据集。"""

    reference: AnalyticsDatasetReference
    columns: tuple[AnalyticsColumn, ...]
    rows: tuple[tuple[JsonValue, ...], ...]
    row_count: int
    truncated: bool
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.rows, tuple) or any(
            not isinstance(row, tuple) for row in self.rows
        ):
            raise TypeError("分析数据行必须使用不可变 tuple")
        if self.row_count != len(self.rows):
            raise ValueError("分析数据集行数与数据不一致")
        if not isinstance(self.columns, tuple):
            raise TypeError("分析数据集必须使用不可变集合")


@runtime_checkable
class AnalyticsDatasetLease(Protocol):
    """受控异步数据集租约。"""

    async def __aenter__(self) -> AnalyticsDataset:
        raise NotImplementedError("进入数据集临时读取边界")

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        raise NotImplementedError("释放数据集临时读取边界")


@runtime_checkable
class AnalyticsFileReader(Protocol):
    """Analytics 文件读取端口。"""

    def open(self, request: AnalyticsFileReadRequest) -> AnalyticsDatasetLease:
        raise NotImplementedError("打开受控分析文件租约")

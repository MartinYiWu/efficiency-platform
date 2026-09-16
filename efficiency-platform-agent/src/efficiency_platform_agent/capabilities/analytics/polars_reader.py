"""Polars 只读分析文件适配器；不执行写入或外部连接。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from .contracts import (
    AnalyticsColumn,
    AnalyticsDataset,
    AnalyticsDatasetLease,
    AnalyticsFileFormat,
    AnalyticsFileReadRequest,
)


class _PolarsDatasetLease:
    """在异步上下文结束时释放本次读取结果。"""

    def __init__(
        self, reader: PolarsAnalyticsFileReader, request: AnalyticsFileReadRequest
    ) -> None:
        self._reader = reader
        self._request = request
        self._dataset: AnalyticsDataset | None = None

    async def __aenter__(self) -> AnalyticsDataset:
        self._dataset = await self._reader.read(self._request)
        return self._dataset

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self._dataset = None


class PolarsAnalyticsFileReader:
    """在受控根目录内读取四种分析文件格式。"""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def open(self, request: AnalyticsFileReadRequest) -> AnalyticsDatasetLease:
        """按 S5 端口打开一次受控数据集租约。"""
        if not isinstance(request, AnalyticsFileReadRequest):
            raise TypeError("分析文件读取请求类型无效")
        return _PolarsDatasetLease(self, request)

    async def read(self, request: AnalyticsFileReadRequest) -> AnalyticsDataset:
        """读取文件并转换为不可变 AnalyticsDataset。"""
        reference = request.dataset_reference
        relative = Path(reference.source_reference)
        target = (self.root / relative).resolve()
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or target.parent != self.root
            or not target.is_file()
        ):
            raise ValueError("ANALYTICS_SOURCE_OUTSIDE_ROOT")
        if target.stat().st_size > request.max_bytes:
            raise ValueError("ANALYTICS_FILE_LIMIT_EXCEEDED")
        return await asyncio.to_thread(self._read, target, request)

    @staticmethod
    def _read(target: Path, request: AnalyticsFileReadRequest) -> AnalyticsDataset:
        fmt = request.dataset_reference.format
        try:
            if fmt is AnalyticsFileFormat.JSON:
                rows_data = json.loads(target.read_text(encoding="utf-8"))
                rows_data = rows_data if isinstance(rows_data, list) else [rows_data]
                columns = (
                    tuple(rows_data[0].keys())
                    if rows_data
                    else request.expected_columns
                )
                rows = [
                    tuple(item.get(column) for column in columns) for item in rows_data
                ]
            else:
                import polars as pl

                if fmt is AnalyticsFileFormat.CSV:
                    frame = pl.read_csv(target)
                elif fmt is AnalyticsFileFormat.PARQUET:
                    frame = pl.read_parquet(target)
                elif fmt is AnalyticsFileFormat.XLSX:
                    frame = pl.read_excel(target)
                else:
                    raise ValueError("分析文件格式不受支持")
                columns = tuple(frame.columns)
                rows = [tuple(row) for row in frame.head(request.max_rows).rows()]
        except Exception as error:
            raise ValueError("ANALYTICS_FORMAT_NOT_AVAILABLE") from error
        if tuple(columns) != request.expected_columns:
            raise ValueError("ANALYTICS_COLUMNS_MISMATCH")
        if len(columns) > request.max_columns or len(rows) > request.max_rows:
            raise ValueError("ANALYTICS_LIMIT_EXCEEDED")
        return AnalyticsDataset(
            request.dataset_reference,
            tuple(AnalyticsColumn(name, "scalar") for name in columns),
            tuple(rows),
            len(rows),
            False,
            (),
        )


__all__ = ["PolarsAnalyticsFileReader"]

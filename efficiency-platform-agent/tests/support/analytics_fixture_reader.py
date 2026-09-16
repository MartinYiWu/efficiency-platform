"""S5 固定 CSV Fixture 的受控读取适配器。"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from efficiency_platform_agent.capabilities.analytics.contracts import (
    AnalyticsColumn,
    AnalyticsDataset,
    AnalyticsDatasetLease,
    AnalyticsFileFormat,
    AnalyticsFileReadRequest,
)


class _FixtureLease:
    """保证正常和异常消费都清理活动数据集。"""

    def __init__(
        self, owner: FixtureAnalyticsFileReader, dataset: AnalyticsDataset
    ) -> None:
        self._owner = owner
        self._dataset = dataset

    async def __aenter__(self) -> AnalyticsDataset:
        self._owner.active_dataset = self._dataset
        return self._dataset

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self._owner.close_count += 1
        self._owner.active_dataset = None
        self._dataset = None  # type: ignore[assignment]


class FixtureAnalyticsFileReader:
    """只允许读取仓库内 analytics Fixture 目录中的 CSV。"""

    def __init__(self, fixture_root: Path | None = None) -> None:
        # 通过固定路径计算避免读取仓库外文件；测试可显式传入同一允许目录。
        self.fixture_root = (
            fixture_root
            or (
                Path(__file__).resolve().parents[1]
                / "fixtures"
                / "operation"
                / "analytics"
            )
        ).resolve()
        self.open_count = 0
        self.close_count = 0
        self.active_dataset: AnalyticsDataset | None = None

    def open(self, request: AnalyticsFileReadRequest) -> AnalyticsDatasetLease:
        self.open_count += 1
        reference = request.dataset_reference
        if reference.format is not AnalyticsFileFormat.CSV:
            raise ValueError("ANALYTICS_FORMAT_NOT_AVAILABLE_IN_S5")
        relative = Path(reference.source_reference)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or relative.name != reference.source_reference
        ):
            raise ValueError("ANALYTICS_SOURCE_OUTSIDE_FIXTURE")
        candidate = self.fixture_root / relative
        if candidate.is_symlink():
            raise ValueError("ANALYTICS_SOURCE_OUTSIDE_FIXTURE")
        target = candidate.resolve()
        if target.parent != self.fixture_root or not target.is_file():
            raise ValueError("ANALYTICS_SOURCE_NOT_ALLOWED")
        if target.stat().st_size > request.max_bytes:
            raise ValueError("ANALYTICS_FILE_LIMIT_EXCEEDED")
        dataset = self._read_csv(target, request)
        return _FixtureLease(self, dataset)

    @staticmethod
    def _read_csv(target: Path, request: AnalyticsFileReadRequest) -> AnalyticsDataset:
        with target.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = tuple(reader.fieldnames or ())
            if columns != request.expected_columns:
                raise ValueError("ANALYTICS_COLUMNS_MISMATCH")
            if len(columns) > request.max_columns:
                raise ValueError("ANALYTICS_COLUMN_LIMIT_EXCEEDED")
            rows: list[tuple[Any, ...]] = []
            for row in reader:
                if len(rows) >= request.max_rows:
                    raise ValueError("ANALYTICS_ROW_LIMIT_EXCEEDED")
                rows.append(
                    (
                        row["date"],
                        row["channel"],
                        int(row["visits"]),
                        int(row["activations"]),
                    )
                )
        return AnalyticsDataset(
            reference=request.dataset_reference,
            columns=(
                AnalyticsColumn("date", "date"),
                AnalyticsColumn("channel", "string"),
                AnalyticsColumn("visits", "integer"),
                AnalyticsColumn("activations", "integer"),
            ),
            rows=tuple(rows),
            row_count=len(rows),
            truncated=False,
            warnings=(),
        )

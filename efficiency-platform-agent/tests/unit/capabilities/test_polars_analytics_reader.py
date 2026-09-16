"""Polars 只读分析端口的离线契约测试。"""

import json
from pathlib import Path

import pytest

from efficiency_platform_agent.capabilities.analytics.contracts import (
    AnalyticsDatasetLease,
    AnalyticsDatasetReference,
    AnalyticsFileFormat,
    AnalyticsFileReadRequest,
)
from efficiency_platform_agent.capabilities.analytics.polars_reader import (
    PolarsAnalyticsFileReader,
)


def _request() -> AnalyticsFileReadRequest:
    return AnalyticsFileReadRequest(
        AnalyticsDatasetReference(
            "analytics-dataset-reference/1",
            "dataset-1",
            "tenant-1",
            AnalyticsFileFormat.JSON,
            "metrics.json",
            "schema-1",
        ),
        None,
        ("date", "channel", "visits"),
        10,
        5,
        1024,
    )


@pytest.mark.asyncio
async def test_reader_implements_s5_open_lease(tmp_path: Path):
    (tmp_path / "metrics.json").write_text(
        json.dumps([{"date": "2026-01-01", "channel": "web", "visits": 10}]),
        encoding="utf-8",
    )
    reader = PolarsAnalyticsFileReader(tmp_path)
    lease = reader.open(_request())
    assert isinstance(lease, AnalyticsDatasetLease)
    async with lease as dataset:
        assert dataset.row_count == 1
        assert dataset.rows == (("2026-01-01", "web", 10),)


@pytest.mark.asyncio
async def test_reader_rejects_source_outside_root(tmp_path: Path):
    request = _request()
    outside = request.__class__(
        AnalyticsDatasetReference(
            "analytics-dataset-reference/1",
            "dataset-1",
            "tenant-1",
            AnalyticsFileFormat.JSON,
            "../metrics.json",
            "schema-1",
        ),
        None,
        request.expected_columns,
        request.max_rows,
        request.max_columns,
        request.max_bytes,
    )
    with pytest.raises(ValueError, match="ANALYTICS_SOURCE_OUTSIDE_ROOT"):
        async with PolarsAnalyticsFileReader(tmp_path).open(outside):
            pass


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("file_format", "filename"),
    [
        (AnalyticsFileFormat.CSV, "analytics_metrics_v1.csv"),
        (AnalyticsFileFormat.JSON, "analytics_metrics_v1.json"),
        (AnalyticsFileFormat.PARQUET, "analytics_metrics_v1.parquet"),
        (AnalyticsFileFormat.XLSX, "analytics_metrics_v1.xlsx"),
    ],
)
async def test_four_fixture_formats_have_the_same_schema_and_row_count(
    file_format: AnalyticsFileFormat, filename: str
):
    root = Path(__file__).parents[2] / "fixtures" / "s7"
    request = AnalyticsFileReadRequest(
        AnalyticsDatasetReference(
            "analytics-dataset-reference/1",
            "dataset-1",
            "tenant-1",
            file_format,
            filename,
            "schema-1",
        ),
        None,
        ("date", "channel", "visits", "activations"),
        10,
        5,
        2_000_000,
    )
    dataset = await PolarsAnalyticsFileReader(root).read(request)
    assert dataset.row_count == 1
    assert tuple(column.name for column in dataset.columns) == request.expected_columns

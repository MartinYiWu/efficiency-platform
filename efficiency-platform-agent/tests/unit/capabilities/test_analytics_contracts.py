"""Analytics 文件读取契约和固定 Fixture 适配器测试。"""

from __future__ import annotations

import pytest

from efficiency_platform_agent.capabilities.analytics.contracts import (
    AnalyticsDatasetReference,
    AnalyticsFileFormat,
    AnalyticsFileReadRequest,
)
from tests.support.analytics_fixture_reader import FixtureAnalyticsFileReader


def valid_request(
    source_reference: str = "operation_metrics_v1.csv",
) -> AnalyticsFileReadRequest:
    return AnalyticsFileReadRequest(
        dataset_reference=AnalyticsDatasetReference(
            contract_version="analytics-dataset-reference/1",
            dataset_id="dataset-1",
            tenant_id="tenant-1",
            format=AnalyticsFileFormat.CSV,
            source_reference=source_reference,
            schema_version="operation-metrics/1",
        ),
        sheet_name=None,
        expected_columns=("date", "channel", "visits", "activations"),
        max_rows=10,
        max_columns=4,
        max_bytes=100_000,
    )


@pytest.mark.asyncio
async def test_fixture_reader_returns_bounded_typed_dataset() -> None:
    reader = FixtureAnalyticsFileReader()
    async with reader.open(valid_request()) as dataset:
        assert dataset.row_count == 6
        assert tuple(column.name for column in dataset.columns) == (
            "date",
            "channel",
            "visits",
            "activations",
        )
    assert (reader.open_count, reader.close_count) == (1, 1)


@pytest.mark.asyncio
async def test_fixture_reader_rejects_escape_and_unsupported_formats() -> None:
    reader = FixtureAnalyticsFileReader()
    for reference in ("../secret.csv", "C:/data/real.xlsx"):
        with pytest.raises(ValueError):
            async with reader.open(valid_request(reference)):
                pytest.fail("非法引用不得进入数据集 lease")


@pytest.mark.asyncio
async def test_fixture_reader_releases_rows_when_consumer_fails() -> None:
    reader = FixtureAnalyticsFileReader()
    with pytest.raises(RuntimeError, match="合成消费失败"):
        async with reader.open(valid_request()):
            raise RuntimeError("合成消费失败")
    assert (reader.open_count, reader.close_count) == (1, 1)
    assert reader.active_dataset is None

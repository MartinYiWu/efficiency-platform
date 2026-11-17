"""窗口发布资产只能显式读取，格式错误不回显资产内容。"""

import pytest

from efficiency_platform_agent.configuration.context_publication import (
    load_context_publication,
)


def test_missing_asset_and_invalid_asset_fail_closed_without_echo(tmp_path):
    with pytest.raises(ValueError, match="^CONTEXT_PUBLICATION_REQUIRED$"):
        load_context_publication(None)
    path = tmp_path / "assets.json"
    for content in (
        "synthetic-secret-marker",
        "{}",
        '{"schema_version":"context-publication/2","metadata":[],"execution_agents":{}}',
    ):
        path.write_text(content, encoding="utf-8")
        with pytest.raises(ValueError, match="^CONTEXT_PUBLICATION_INVALID$") as error:
            load_context_publication(path)
        assert "synthetic-secret-marker" not in str(error.value)


def test_declared_asset_size_is_bounded_before_reading(tmp_path):
    path = tmp_path / "oversized.json"
    with path.open("wb") as output:
        output.seek(4_194_304)
        output.write(b"x")
    with pytest.raises(ValueError, match="^CONTEXT_PUBLICATION_INVALID$"):
        load_context_publication(path)

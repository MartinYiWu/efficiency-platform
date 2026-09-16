"""S7 Gate 配置文件的名称和默认关闭治理测试。"""

import tomllib
from pathlib import Path


def test_gate_config_matches_enum_and_keeps_all_gates_closed():
    path = Path(__file__).parents[2] / "config" / "integration-gates.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    expected = {
        "deepseek_chat",
        "deepseek_web_search",
        "postgres_pgvector",
        "redis_taskiq",
        "cos_artifact",
        "document_pipeline",
        "end_to_end",
    }
    assert set(data["gates"]) == expected
    assert all(value is False for value in data["gates"].values())


def test_gate_config_limits_are_non_sensitive_and_bounded():
    path = Path(__file__).parents[2] / "config" / "integration-gates.toml"
    limits = tomllib.loads(path.read_text(encoding="utf-8"))["limits"]
    assert limits["max_search_calls"] == 4
    assert limits["max_redis_records"] == 20
    assert limits["max_cos_objects"] == 3
    assert all(isinstance(value, int) and value >= 0 for value in limits.values())

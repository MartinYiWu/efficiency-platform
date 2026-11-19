"""Agent自有PostgreSQL schema的纯命名合同，不访问配置或数据库。"""

import re


class InvalidPostgresSchema(ValueError):
    """目标 Schema 不符合 S7 隔离命名规则。"""


SCHEMA_PATTERN = re.compile(r"^s7_acceptance_[a-f0-9]{8}$")
AGENT_RUNTIME_SCHEMA_PATTERN = re.compile(r"^agent_runtime(?:_[a-f0-9]{8})?$")


def validate_schema(schema: str) -> str:
    """校验并返回只含固定字符集的 S7 Schema。"""
    if not isinstance(schema, str) or SCHEMA_PATTERN.fullmatch(schema) is None:
        raise InvalidPostgresSchema("Schema 必须匹配 s7_acceptance_[a-f0-9]{8}")
    return schema


def validate_agent_owned_schema(schema: str) -> str:
    """允许 S7 隔离 schema 或正式 Agent Runtime 独立 schema。"""

    if SCHEMA_PATTERN.fullmatch(schema) or AGENT_RUNTIME_SCHEMA_PATTERN.fullmatch(
        schema
    ):
        return schema
    raise InvalidPostgresSchema("Schema 不属于 Agent 独立命名空间")

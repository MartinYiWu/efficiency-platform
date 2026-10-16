"""MySQL Prompt 资产读取与 Run 快照持久化。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from sqlalchemy import bindparam, text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from .contracts import (
    ModelPolicy,
    OutputContract,
    PromptBundle,
    PromptDefinition,
    PromptMessageTemplate,
    PromptVariableDefinition,
    PromptVersion,
    RunPromptSnapshot,
)
from .repository import PromptConfigurationError

_STATIC_ROLES = {"system", "developer", "user", "assistant"}
_TRUSTED_ROLES = {"system", "developer"}
_VALUE_SOURCES = {"system_context", "user_input", "research_data", "artifact"}
_VALUE_TYPES = {"string", "integer", "boolean", "json", "string_list"}


def validate_prompt_bundle(bundle: PromptBundle) -> PromptBundle:
    """校验数据库行之间的引用关系和 Prompt 信任边界。"""
    if not bundle.definition.enabled or bundle.version.status != "released":
        raise PromptConfigurationError("PROMPT_NOT_RELEASED")
    if bundle.version.prompt_definition_id != bundle.definition.id:
        raise PromptConfigurationError("PROMPT_REFERENCE_INVALID", "definition")
    if bundle.version.model_policy_id != bundle.model_policy.id:
        raise PromptConfigurationError("PROMPT_REFERENCE_INVALID", "model_policy")
    if bundle.version.output_contract_id != bundle.output_contract.id:
        raise PromptConfigurationError("PROMPT_REFERENCE_INVALID", "output_contract")
    _verify_checksum(
        bundle.model_policy.checksum,
        {
            "key": bundle.model_policy.policy_key,
            "version": bundle.model_policy.semantic_version,
        },
        "model_policy",
    )
    _verify_checksum(
        bundle.output_contract.checksum,
        bundle.output_contract.json_schema,
        "output_contract",
    )
    _verify_checksum(
        bundle.version.checksum,
        {
            "prompt_key": bundle.definition.prompt_key,
            "version": bundle.version.semantic_version,
        },
        "prompt_version",
    )
    if not bundle.messages:
        raise PromptConfigurationError("PROMPT_MESSAGE_MISSING")

    message_ids: set[int] = set()
    ordinals: set[int] = set()
    message_keys: set[str] = set()
    for message in bundle.messages:
        if message.prompt_version_id != bundle.version.id:
            raise PromptConfigurationError("PROMPT_REFERENCE_INVALID", "message")
        if message.role not in _STATIC_ROLES:
            raise PromptConfigurationError("PROMPT_ROLE_INVALID", message.role)
        if message.trusted_instruction and message.role not in _TRUSTED_ROLES:
            raise PromptConfigurationError(
                "PROMPT_TRUST_BOUNDARY_INVALID", message.message_key
            )
        _verify_checksum(
            message.checksum,
            {"role": message.role, "content": message.content_template},
            f"message:{message.message_key}",
        )
        if message.ordinal in ordinals or message.message_key in message_keys:
            raise PromptConfigurationError("PROMPT_MESSAGE_DUPLICATE")
        message_ids.add(message.id)
        ordinals.add(message.ordinal)
        message_keys.add(message.message_key)

    for variable in bundle.variables:
        if variable.prompt_message_template_id not in message_ids:
            raise PromptConfigurationError("PROMPT_REFERENCE_INVALID", "variable")
        if variable.value_source not in _VALUE_SOURCES:
            raise PromptConfigurationError(
                "PROMPT_VARIABLE_SOURCE_INVALID", variable.variable_name
            )
        if variable.value_type not in _VALUE_TYPES:
            raise PromptConfigurationError(
                "PROMPT_VARIABLE_TYPE_INVALID", variable.variable_name
            )
        message = next(
            item
            for item in bundle.messages
            if item.id == variable.prompt_message_template_id
        )
        if message.role in _TRUSTED_ROLES and (
            variable.value_source != "system_context"
            or variable.allow_untrusted_content
        ):
            raise PromptConfigurationError(
                "PROMPT_TRUST_BOUNDARY_INVALID", variable.variable_name
            )
    return bundle


class MySqlPromptRepository:
    """只解析显式发布版本，不以最新创建时间推断线上 Prompt。"""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def resolve(self, prompt_key: str, environment: str) -> PromptBundle:
        try:
            async with self._engine.connect() as connection:
                result = await connection.execute(
                    text(
                        """
                        SELECT r.prompt_version_id
                        FROM agent_prompt_release r
                        JOIN agent_prompt_definition d
                          ON d.id = r.prompt_definition_id
                        WHERE r.environment = :environment
                          AND d.prompt_key = :prompt_key
                          AND d.enabled = 1
                        """
                    ),
                    {"environment": environment, "prompt_key": prompt_key},
                )
                version_id = result.scalar_one_or_none()
                if version_id is None:
                    raise PromptConfigurationError(
                        "PROMPT_RELEASE_NOT_FOUND",
                        f"{environment}:{prompt_key}",
                    )
                return await self._load_bundle(connection, int(version_id))
        except PromptConfigurationError:
            raise
        except SQLAlchemyError as exc:
            raise PromptConfigurationError(
                "PROMPT_REPOSITORY_UNAVAILABLE", str(exc)
            ) from exc

    async def load_snapshot(
        self, run_id: str, stage: str
    ) -> PromptBundle | None:
        try:
            async with self._engine.connect() as connection:
                result = await connection.execute(
                    text(
                        """
                        SELECT prompt_version_id
                        FROM agent_run_prompt_snapshot
                        WHERE run_id = :run_id AND stage_key = :stage_key
                        """
                    ),
                    {"run_id": run_id, "stage_key": stage},
                )
                version_id = result.scalar_one_or_none()
                if version_id is None:
                    return None
                return await self._load_bundle(connection, int(version_id))
        except PromptConfigurationError:
            raise
        except SQLAlchemyError as exc:
            raise PromptConfigurationError(
                "PROMPT_REPOSITORY_UNAVAILABLE", str(exc)
            ) from exc

    async def save_snapshot(self, snapshot: RunPromptSnapshot) -> None:
        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    text(
                        """
                        INSERT INTO agent_run_prompt_snapshot (
                            run_id, stage_key, prompt_definition_id,
                            prompt_version_id, model_policy_id,
                            output_contract_id, message_checksum,
                            rendered_messages_checksum, variable_values_checksum,
                            referenced_snapshot_json, created_at_epoch_ms
                        ) VALUES (
                            :run_id, :stage_key, :prompt_definition_id,
                            :prompt_version_id, :model_policy_id,
                            :output_contract_id, :message_checksum,
                            :rendered_messages_checksum, :variable_values_checksum,
                            :referenced_snapshot_json, :created_at_epoch_ms
                        )
                        """
                    ),
                    {
                        "run_id": snapshot.run_id,
                        "stage_key": snapshot.stage,
                        "prompt_definition_id": snapshot.prompt_definition_id,
                        "prompt_version_id": snapshot.prompt_version_id,
                        "model_policy_id": snapshot.model_policy_id,
                        "output_contract_id": snapshot.output_contract_id,
                        "message_checksum": snapshot.message_checksum,
                        "rendered_messages_checksum": snapshot.rendered_messages_checksum,
                        "variable_values_checksum": snapshot.variable_values_checksum,
                        "referenced_snapshot_json": json.dumps(
                            snapshot.referenced_snapshot,
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        "created_at_epoch_ms": snapshot.created_at_epoch_ms,
                    },
                )
        except SQLAlchemyError as exc:
            raise PromptConfigurationError(
                "PROMPT_SNAPSHOT_SAVE_FAILED", str(exc)
            ) from exc

    async def _load_bundle(
        self, connection: AsyncConnection, version_id: int
    ) -> PromptBundle:
        header = await connection.execute(
            text(
                """
                SELECT
                    d.id AS d_id, d.prompt_key, d.scenario,
                    d.stage_key, d.platform, d.name, d.description,
                    d.enabled AS d_enabled,
                    v.id AS v_id, v.semantic_version AS v_semantic_version,
                    v.status, v.model_policy_id, v.output_contract_id,
                    v.checksum AS v_checksum,
                    p.id AS p_id, p.policy_key,
                    p.semantic_version AS p_semantic_version,
                    p.provider, p.model_name, p.temperature, p.top_p,
                    p.max_input_tokens, p.max_output_tokens,
                    p.connect_timeout_ms, p.read_timeout_ms,
                    p.max_retries, p.max_tool_calls, p.checksum AS p_checksum,
                    o.id AS o_id, o.contract_key,
                    o.semantic_version AS o_semantic_version,
                    o.json_schema, o.field_description,
                    o.checksum AS o_checksum
                FROM agent_prompt_version v
                JOIN agent_prompt_definition d ON d.id = v.prompt_definition_id
                JOIN agent_model_policy p ON p.id = v.model_policy_id
                JOIN agent_output_contract o ON o.id = v.output_contract_id
                WHERE v.id = :version_id AND p.enabled = 1 AND o.enabled = 1
                """
            ),
            {"version_id": version_id},
        )
        row = header.mappings().one_or_none()
        if row is None:
            raise PromptConfigurationError(
                "PROMPT_VERSION_NOT_FOUND", str(version_id)
            )

        message_result = await connection.execute(
            text(
                """
                SELECT id, prompt_version_id, ordinal, role, message_key,
                       content_template, content_format,
                       trusted_instruction, checksum
                FROM agent_prompt_message_template
                WHERE prompt_version_id = :version_id
                ORDER BY ordinal
                """
            ),
            {"version_id": version_id},
        )
        message_rows = tuple(message_result.mappings())
        messages = tuple(self._decode_message(item) for item in message_rows)
        message_ids = [item.id for item in messages]
        variable_rows: tuple[RowMapping, ...] = ()
        if message_ids:
            variable_result = await connection.execute(
                text(
                    """
                    SELECT id, prompt_message_template_id, variable_name,
                           value_type, value_source, required, sensitive,
                           max_length, allow_untrusted_content
                    FROM agent_prompt_variable
                    WHERE prompt_message_template_id IN :message_ids
                    ORDER BY prompt_message_template_id, id
                    """
                ).bindparams(bindparam("message_ids", expanding=True)),
                {"message_ids": message_ids},
            )
            variable_rows = tuple(variable_result.mappings())

        bundle = PromptBundle(
            definition=PromptDefinition(
                int(row["d_id"]),
                str(row["prompt_key"]),
                str(row["scenario"]),
                str(row["stage_key"]),
                _optional_str(row["platform"]),
                str(row["name"]),
                str(row["description"]),
                bool(row["d_enabled"]),
            ),
            version=PromptVersion(
                int(row["v_id"]),
                int(row["d_id"]),
                str(row["v_semantic_version"]),
                str(row["status"]),
                int(row["model_policy_id"]),
                int(row["output_contract_id"]),
                str(row["v_checksum"]),
            ),
            messages=messages,
            variables=tuple(self._decode_variable(item) for item in variable_rows),
            model_policy=ModelPolicy(
                int(row["p_id"]),
                str(row["policy_key"]),
                str(row["p_semantic_version"]),
                str(row["provider"]),
                str(row["model_name"]),
                float(row["temperature"]),
                None if row["top_p"] is None else float(row["top_p"]),
                int(row["max_input_tokens"]),
                int(row["max_output_tokens"]),
                int(row["connect_timeout_ms"]),
                int(row["read_timeout_ms"]),
                int(row["max_retries"]),
                int(row["max_tool_calls"]),
                str(row["p_checksum"]),
            ),
            output_contract=OutputContract(
                int(row["o_id"]),
                str(row["contract_key"]),
                str(row["o_semantic_version"]),
                _decode_json_object(row["json_schema"]),
                str(row["field_description"]),
                str(row["o_checksum"]),
            ),
        )
        return validate_prompt_bundle(bundle)

    @staticmethod
    def _decode_message(row: RowMapping) -> PromptMessageTemplate:
        return PromptMessageTemplate(
            int(row["id"]),
            int(row["prompt_version_id"]),
            int(row["ordinal"]),
            str(row["role"]),
            str(row["message_key"]),
            str(row["content_template"]),
            str(row["content_format"]),
            bool(row["trusted_instruction"]),
            str(row["checksum"]),
        )

    @staticmethod
    def _decode_variable(row: RowMapping) -> PromptVariableDefinition:
        return PromptVariableDefinition(
            int(row["id"]),
            int(row["prompt_message_template_id"]),
            str(row["variable_name"]),
            str(row["value_type"]),
            str(row["value_source"]),
            bool(row["required"]),
            bool(row["sensitive"]),
            int(row["max_length"]),
            bool(row["allow_untrusted_content"]),
        )


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _decode_json_object(value: object) -> Mapping[str, object]:
    decoded = json.loads(value) if isinstance(value, str) else value
    if not isinstance(decoded, Mapping):
        raise PromptConfigurationError("PROMPT_OUTPUT_SCHEMA_INVALID")
    return dict(decoded)


def _verify_checksum(stored: str, value: object, asset: str) -> None:
    expected = _checksum(value)
    if stored != expected:
        raise PromptConfigurationError("PROMPT_CHECKSUM_INVALID", asset)


def _checksum(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = ["MySqlPromptRepository", "validate_prompt_bundle"]

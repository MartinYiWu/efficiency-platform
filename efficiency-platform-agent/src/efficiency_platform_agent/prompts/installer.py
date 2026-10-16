"""开发环境 Prompt 初始资产的幂等安装。"""

from __future__ import annotations

import json
import time
from dataclasses import asdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from .contracts import PromptSeedPackage


async def install_prompt_seed(engine: AsyncEngine, seed: PromptSeedPackage) -> None:
    """只插入不可变资产；已存在的 dev release 允许切到同包版本。"""

    now = int(time.time() * 1000)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                INSERT INTO agent_model_policy (
                    id, policy_key, semantic_version, provider, model_name,
                    temperature, top_p, max_input_tokens, max_output_tokens,
                    connect_timeout_ms, read_timeout_ms, max_retries,
                    max_tool_calls, enabled, checksum, created_at_epoch_ms
                ) VALUES (
                    :id, :policy_key, :semantic_version, :provider, :model_name,
                    :temperature, :top_p, :max_input_tokens, :max_output_tokens,
                    :connect_timeout_ms, :read_timeout_ms, :max_retries,
                    :max_tool_calls, 1, :checksum, :created_at_epoch_ms
                )
                ON DUPLICATE KEY UPDATE id = id
                """
            ),
            [
                {
                    **asdict(item),
                    "created_at_epoch_ms": now,
                }
                for item in seed.model_policies
            ],
        )
        await connection.execute(
            text(
                """
                INSERT INTO agent_output_contract (
                    id, contract_key, semantic_version, json_schema,
                    field_description, checksum, enabled, created_at_epoch_ms
                ) VALUES (
                    :id, :contract_key, :semantic_version, :json_schema,
                    :field_description, :checksum, 1, :created_at_epoch_ms
                )
                ON DUPLICATE KEY UPDATE id = id
                """
            ),
            [
                {
                    "id": item.id,
                    "contract_key": item.contract_key,
                    "semantic_version": item.semantic_version,
                    "json_schema": json.dumps(item.json_schema, ensure_ascii=False),
                    "field_description": item.field_description,
                    "checksum": item.checksum,
                    "created_at_epoch_ms": now,
                }
                for item in seed.output_contracts
            ],
        )
        await connection.execute(
            text(
                """
                INSERT INTO agent_prompt_definition (
                    id, prompt_key, scenario, stage_key, platform, name,
                    description, enabled, created_at_epoch_ms, updated_at_epoch_ms
                ) VALUES (
                    :id, :prompt_key, :scenario, :stage_key, :platform, :name,
                    :description, :enabled, :created_at_epoch_ms, :updated_at_epoch_ms
                )
                ON DUPLICATE KEY UPDATE id = id
                """
            ),
            [
                {
                    "id": item.id,
                    "prompt_key": item.prompt_key,
                    "scenario": item.scenario,
                    "stage_key": item.stage,
                    "platform": item.platform,
                    "name": item.name,
                    "description": item.description,
                    "enabled": item.enabled,
                    "created_at_epoch_ms": now,
                    "updated_at_epoch_ms": now,
                }
                for item in seed.definitions
            ],
        )
        await connection.execute(
            text(
                """
                INSERT INTO agent_prompt_version (
                    id, prompt_definition_id, semantic_version, status,
                    model_policy_id, output_contract_id, checksum,
                    change_summary, created_by, created_at_epoch_ms,
                    released_at_epoch_ms, supersedes_version_id
                ) VALUES (
                    :id, :prompt_definition_id, :semantic_version, :status,
                    :model_policy_id, :output_contract_id, :checksum,
                    '运营助手全功能 Agent 初始版本', 'codex', :created_at_epoch_ms,
                    :released_at_epoch_ms, NULL
                )
                ON DUPLICATE KEY UPDATE id = id
                """
            ),
            [
                {
                    **asdict(item),
                    "created_at_epoch_ms": now,
                    "released_at_epoch_ms": now,
                }
                for item in seed.versions
            ],
        )
        await connection.execute(
            text(
                """
                INSERT INTO agent_prompt_message_template (
                    id, prompt_version_id, ordinal, role, message_key,
                    content_template, content_format, trusted_instruction, checksum
                ) VALUES (
                    :id, :prompt_version_id, :ordinal, :role, :message_key,
                    :content_template, :content_format, :trusted_instruction, :checksum
                )
                ON DUPLICATE KEY UPDATE id = id
                """
            ),
            [asdict(item) for item in seed.messages],
        )
        await connection.execute(
            text(
                """
                INSERT INTO agent_prompt_variable (
                    id, prompt_message_template_id, variable_name, value_type,
                    value_source, is_required, is_sensitive, max_length,
                    allow_untrusted_content
                ) VALUES (
                    :id, :prompt_message_template_id, :variable_name, :value_type,
                    :value_source, :required, :sensitive, :max_length,
                    :allow_untrusted_content
                )
                ON DUPLICATE KEY UPDATE id = id
                """
            ),
            [asdict(item) for item in seed.variables],
        )
        await connection.execute(
            text(
                """
                INSERT INTO agent_prompt_release (
                    environment, prompt_definition_id, prompt_version_id,
                    released_by, released_at_epoch_ms
                ) VALUES (
                    :environment, :prompt_definition_id, :prompt_version_id,
                    'codex', :released_at_epoch_ms
                )
                ON DUPLICATE KEY UPDATE id = id
                """
            ),
            [
                {
                    **asdict(item),
                    "released_at_epoch_ms": now,
                }
                for item in seed.releases
            ],
        )
        await connection.execute(
            text(
                """
                UPDATE agent_prompt_release
                SET prompt_version_id = :prompt_version_id,
                    released_by = 'codex',
                    released_at_epoch_ms = :released_at_epoch_ms
                WHERE environment = :environment
                  AND prompt_definition_id = :prompt_definition_id
                """
            ),
            [
                {
                    **asdict(item),
                    "released_at_epoch_ms": now,
                }
                for item in seed.releases
            ],
        )


__all__ = ["install_prompt_seed"]

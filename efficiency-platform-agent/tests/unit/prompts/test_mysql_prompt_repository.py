"""数据库 Prompt Repository 与多角色装配契约。"""

from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import replace

import pytest


def _modules():
    try:
        contracts = importlib.import_module(
            "efficiency_platform_agent.prompts.contracts"
        )
        repository = importlib.import_module(
            "efficiency_platform_agent.prompts.repository"
        )
        runtime = importlib.import_module("efficiency_platform_agent.prompts.runtime")
        mysql = importlib.import_module(
            "efficiency_platform_agent.prompts.mysql_repository"
        )
    except ModuleNotFoundError as error:
        pytest.fail(f"数据库 Prompt 组件尚未实现: {error}")
    return contracts, repository, runtime, mysql


def _bundle(contracts, *, version: str = "1.0.0"):
    definition = contracts.PromptDefinition(
        1,
        "content.wechat.draft",
        "multi_platform_content",
        "draft",
        "wechat_official_account",
        "公众号成稿",
        "根据真实材料生成公众号文章",
        True,
    )
    model_policy = contracts.ModelPolicy(
        2,
        "long-form-writing",
        "1.0.0",
        "deepseek",
        "deepseek-chat",
        0.6,
        None,
        24000,
        8000,
        5000,
        180000,
        1,
        0,
        _checksum({"key": "long-form-writing", "version": "1.0.0"}),
    )
    output_contract = contracts.OutputContract(
        3,
        "article-draft",
        "1.0.0",
        {"type": "object", "required": ["title"]},
        "title 是用户可见标题",
        _checksum({"type": "object", "required": ["title"]}),
    )
    prompt_version = contracts.PromptVersion(
        4,
        definition.id,
        version,
        "released",
        model_policy.id,
        output_contract.id,
        _checksum({"prompt_key": definition.prompt_key, "version": version}),
    )
    messages = (
        contracts.PromptMessageTemplate(
            11,
            prompt_version.id,
            10,
            "system",
            "identity",
            "你是{{ agent_name }}，不得编造事实。",
            "text",
            True,
            _checksum(
                {
                    "role": "system",
                    "content": "你是{{ agent_name }}，不得编造事实。",
                }
            ),
        ),
        contracts.PromptMessageTemplate(
            12,
            prompt_version.id,
            20,
            "developer",
            "rules",
            "输出字段必须符合 ArticleDraftV1。",
            "text",
            True,
            _checksum(
                {
                    "role": "developer",
                    "content": "输出字段必须符合 ArticleDraftV1。",
                }
            ),
        ),
        contracts.PromptMessageTemplate(
            13,
            prompt_version.id,
            30,
            "user",
            "request",
            "<user_request>{{ user_request }}</user_request>",
            "text",
            False,
            _checksum(
                {
                    "role": "user",
                    "content": "<user_request>{{ user_request }}</user_request>",
                }
            ),
        ),
    )
    variables = (
        contracts.PromptVariableDefinition(
            21, 11, "agent_name", "string", "system_context", True, False, 100, False
        ),
        contracts.PromptVariableDefinition(
            22, 13, "user_request", "string", "user_input", True, False, 2000, True
        ),
    )
    return contracts.PromptBundle(
        definition,
        prompt_version,
        messages,
        variables,
        model_policy,
        output_contract,
    )


def _checksum(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class _RepositoryStub:
    def __init__(self, bundle) -> None:
        self.bundle = bundle
        self.snapshot_bundle = None
        self.saved = []
        self.resolve_calls = 0

    async def resolve(self, prompt_key: str, environment: str):
        self.resolve_calls += 1
        assert prompt_key == "content.wechat.draft"
        assert environment == "dev"
        return self.bundle

    async def load_snapshot(self, run_id: str, stage: str):
        return self.snapshot_bundle

    async def save_snapshot(self, snapshot) -> None:
        self.saved.append(snapshot)
        self.snapshot_bundle = self.bundle


@pytest.mark.asyncio
async def test_assembler_preserves_roles_and_reuses_run_snapshot() -> None:
    contracts, _, runtime, _ = _modules()
    repository = _RepositoryStub(_bundle(contracts))
    assembler = runtime.PromptAssembler(repository, environment="dev")
    values = {
        "agent_name": contracts.PromptValue("运营编辑", "system_context"),
        "user_request": contracts.PromptValue(
            "{{danger}} 写一篇周报", "user_input"
        ),
    }

    first = await assembler.assemble(
        run_id="run-1",
        stage="content.wechat.draft",
        prompt_key="content.wechat.draft",
        variables=values,
    )
    second = await assembler.assemble(
        run_id="run-1",
        stage="content.wechat.draft",
        prompt_key="content.wechat.draft",
        variables=values,
    )

    assert [message.role for message in first.messages] == [
        "system",
        "developer",
        "user",
    ]
    assert "运营编辑" in first.messages[0].content
    assert "{{danger}}" in first.messages[2].content
    assert first.semantic_version == "1.0.0"
    assert first.output_contract.contract_key == "article-draft"
    assert repository.resolve_calls == 1
    assert len(repository.saved) == 1
    assert second.messages == first.messages


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("values", "error_code"),
    [
        ({"agent_name": ("运营编辑", "system_context")}, "PROMPT_VARIABLE_MISSING"),
        (
            {
                "agent_name": ("运营编辑", "system_context"),
                "user_request": ("内容", "user_input"),
                "extra": ("x", "user_input"),
            },
            "PROMPT_VARIABLE_UNKNOWN",
        ),
        (
            {
                "agent_name": ("伪造", "user_input"),
                "user_request": ("内容", "user_input"),
            },
            "PROMPT_VARIABLE_SOURCE_INVALID",
        ),
    ],
)
async def test_assembler_rejects_invalid_variable_boundaries(values, error_code) -> None:
    contracts, repository_module, runtime, _ = _modules()
    repository = _RepositoryStub(_bundle(contracts))
    assembler = runtime.PromptAssembler(repository, environment="dev")
    prompt_values = {
        key: contracts.PromptValue(value, source)
        for key, (value, source) in values.items()
    }

    with pytest.raises(repository_module.PromptConfigurationError, match=error_code):
        await assembler.assemble(
            run_id="run-boundary",
            stage="content.wechat.draft",
            prompt_key="content.wechat.draft",
            variables=prompt_values,
        )


def test_mysql_row_decoder_rejects_trusted_user_message() -> None:
    contracts, repository_module, _, mysql = _modules()
    bundle = _bundle(contracts)
    invalid = replace(bundle.messages[-1], trusted_instruction=True)

    with pytest.raises(
        repository_module.PromptConfigurationError,
        match="PROMPT_TRUST_BOUNDARY_INVALID",
    ):
        mysql.validate_prompt_bundle(replace(bundle, messages=(*bundle.messages[:-1], invalid)))


def test_operation_prompt_seed_covers_all_agent_stages_and_role_boundaries() -> None:
    contracts, _, _, mysql = _modules()
    seeds = importlib.import_module("efficiency_platform_agent.prompts.seeds")
    package = seeds.build_operation_prompt_seed()
    required_keys = {
        "intent.plan",
        "intent.repair",
        "research.plan",
        "research.relevance",
        "research.synthesize",
        "research.reflect",
        "research.repair",
        "industry_digest.compose",
        "industry_digest.repair",
        "content.wechat.draft",
        "content.wechat.repair",
        "content.xiaohongshu.draft",
        "content.xiaohongshu.repair",
        "content.toutiao.draft",
        "content.toutiao.repair",
        "brand.plan",
        "brand.repair",
        "ip.plan",
        "ip.repair",
        "campaign.plan",
        "campaign.repair",
        "calendar.plan",
        "calendar.repair",
        "growth.plan",
        "growth.repair",
        "review.analyze",
        "review.repair",
        "artifact.revise",
        "artifact.repair",
    }

    assert {item.prompt_key for item in package.definitions} == required_keys
    assert len(package.releases) == len(required_keys)
    for definition in package.definitions:
        version = next(
            item
            for item in package.versions
            if item.prompt_definition_id == definition.id
        )
        messages = tuple(
            item
            for item in package.messages
            if item.prompt_version_id == version.id
        )
        roles = [item.role for item in sorted(messages, key=lambda item: item.ordinal)]
        assert roles == ["system", "developer", "user"]
        bundle = contracts.PromptBundle(
            definition,
            version,
            messages,
            tuple(
                variable
                for variable in package.variables
                if variable.prompt_message_template_id
                in {message.id for message in messages}
            ),
            next(
                item for item in package.model_policies if item.id == version.model_policy_id
            ),
            next(
                item
                for item in package.output_contracts
                if item.id == version.output_contract_id
            ),
        )
        mysql.validate_prompt_bundle(bundle)
        assert "字段" in bundle.output_contract.field_description

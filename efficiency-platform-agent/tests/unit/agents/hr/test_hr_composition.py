from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from efficiency_platform_agent.configuration.integration import S7IntegrationSettings


def test_hr_is_closed_by_default_and_secret_comes_only_from_explicit_env(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("AGENT_HR_ENABLED", "true")
    path = tmp_path / ".env"
    path.write_text("AGENT_HR_ENABLED=false\n", encoding="utf-8")
    settings = S7IntegrationSettings.from_env_file(path)
    assert settings.hr_enabled is False and settings.hr_internal_secret is None
    path.write_text(
        "AGENT_HR_ENABLED=true\nAGENT_HR_INTERNAL_SECRET="
        + ("s" * 32)
        + "\nAGENT_HR_OCR_DETECTION_MODEL_DIR=local/det\nAGENT_HR_OCR_RECOGNITION_MODEL_DIR=local/rec\n",
        encoding="utf-8",
    )
    settings = S7IntegrationSettings.from_env_file(path)
    assert settings.hr_enabled is True
    assert isinstance(settings.hr_internal_secret, SecretStr)
    assert settings.hr_ocr_detection_model_dir == Path("local/det")
    assert "s" * 32 not in repr(settings)


def test_enabled_hr_missing_internal_identity_fails_closed():
    with pytest.raises(ValidationError, match="HR_INTERNAL_AUTH_CONFIG_REQUIRED"):
        S7IntegrationSettings(hr_enabled=True)


def test_enabled_hr_fake_factory_without_published_prompt_storage_fails_closed():
    from efficiency_platform_agent.harness.local_real_factory import (
        build_local_agent_application,
    )
    from efficiency_platform_agent.providers.llm.fake import FakeModelProvider

    with pytest.raises(ValueError, match="HR_CONFIG_PROMPT_STORAGE_REQUIRED"):
        build_local_agent_application(
            S7IntegrationSettings(
                hr_enabled=True, hr_internal_secret=SecretStr("s" * 32)
            ),
            provider=FakeModelProvider("synthetic", []),
            test_mode=True,
        )


@pytest.mark.asyncio
async def test_default_fake_factory_does_not_expose_hr_execution():
    import httpx

    from efficiency_platform_agent.harness.local_real_factory import (
        build_local_agent_application,
    )
    from efficiency_platform_agent.providers.llm.fake import FakeModelProvider
    from tests.unit.harness.test_local_real_factory import synthetic_settings

    application = build_local_agent_application(
        synthetic_settings(),
        provider=FakeModelProvider("synthetic", []),
        test_mode=True,
    )
    try:
        assert application.app.state.hr_enabled is False
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application.app), base_url="http://test"
        ) as client:
            response = await client.post("/skill/execute", json={})
        assert response.status_code == 503
    finally:
        await application.close()


@pytest.mark.asyncio
async def test_hr_model_route_uses_exact_published_logical_model_and_rejects_unknown():
    from efficiency_platform_agent.core.run import (
        JsonObject,
        ProviderMessage,
        ProviderRequest,
        ProviderResult,
        ProviderUsage,
    )
    from efficiency_platform_agent.harness.hr_factory import HrPolicyModelProvider
    from efficiency_platform_agent.providers.llm.fake import FakeModelProvider

    expected = ProviderResult(
        "provider-result/1",
        ProviderMessage("assistant", "{}"),
        ProviderUsage(0, 0, 0, 0, 0),
    )
    selected = FakeModelProvider("selected", [expected])
    route = HrPolicyModelProvider({"hr-approved-model": selected})
    request = ProviderRequest(
        "provider-request/1",
        (ProviderMessage("user", "{}"),),
        JsonObject((("logical_model", "hr-approved-model"),)),
        1000,
    )
    assert await route.complete(request) == expected
    with pytest.raises(ValueError, match="HR_CONFIG_MODEL_PROVIDER_MISSING"):
        await route.complete(
            ProviderRequest(
                "provider-request/1",
                request.messages,
                JsonObject((("logical_model", "unknown-model"),)),
                1000,
            )
        )


def test_offline_hr_asset_pack_matches_runtime_schemas_and_is_unpublished():
    import json

    from efficiency_platform_agent.contracts.hr import (
        EvaluationOutput,
        ExplanationOutput,
        FactOutput,
        HrSkillRequest,
        InterviewOutput,
        JdOutput,
    )

    asset = json.loads(
        (
            Path(__file__).resolve().parents[5]
            / "docs/ai-assets/hr/hr-prompt-contracts-draft.json"
        ).read_text(encoding="utf-8")
    )
    assert asset["status"] == "DRAFT_NOT_PUBLISHED"
    assert asset["input_schema"] == HrSkillRequest.model_json_schema()
    outputs = {
        "hr.resume.structure": FactOutput,
        "hr.requirements.evaluate": EvaluationOutput,
        "hr.match.explain": ExplanationOutput,
        "hr.interview.generate": InterviewOutput,
        "hr.jd.draft": JdOutput,
    }
    for skill, output in outputs.items():
        item = next(x for x in asset["prompts"] if x["prompt_key"] == skill)
        assert item["output_schema"] == output.model_json_schema()
        assert item["status"] == "draft"
        assert item["model_policy"]["model_name"] is None


@pytest.mark.asyncio
async def test_hr_readiness_refuses_unpublished_prompts_without_provider_calls():
    from efficiency_platform_agent.harness.hr_factory import validate_hr_prompt_assets
    from efficiency_platform_agent.prompts.repository import PromptConfigurationError

    class Repository:
        async def resolve(self, key, environment):
            raise PromptConfigurationError("PROMPT_NOT_RELEASED")

    with pytest.raises(PromptConfigurationError, match="PROMPT_NOT_RELEASED"):
        await validate_hr_prompt_assets(Repository(), {"approved"})

from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class LlmConfigurationTemplateTest(unittest.TestCase):
    @staticmethod
    def assert_assignments_have_chinese_comments(lines: list[str]) -> None:
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue

            previous = lines[index - 1].strip() if index else ""
            has_chinese_comment = previous.startswith("#") and any(
                "\u4e00" <= character <= "\u9fff" for character in previous
            )
            if not has_chinese_comment:
                raise AssertionError(f"配置项缺少紧邻的中文说明：{stripped.split('=', 1)[0]}")

    @staticmethod
    def read_env_values(path: Path) -> dict[str, str]:
        return {
            key: value
            for line in path.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#") and "=" in line
            for key, value in [line.split("=", maxsplit=1)]
        }

    @staticmethod
    def assert_rules_have_chinese_comments(lines: list[str]) -> None:
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            previous = lines[index - 1].strip() if index else ""
            has_chinese_comment = previous.startswith("#") and any(
                "\u4e00" <= character <= "\u9fff" for character in previous
            )
            if not has_chinese_comment:
                raise AssertionError(f"忽略规则缺少紧邻的中文说明：{stripped}")

    def test_shared_configuration_assignments_have_chinese_comments(self) -> None:
        self.assert_assignments_have_chinese_comments(
            (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        )
        self.assert_assignments_have_chinese_comments(
            (PROJECT_ROOT / "config" / "llm-routing.toml").read_text(encoding="utf-8").splitlines()
        )

    def test_local_env_assignments_have_chinese_comments_when_present(self) -> None:
        local_env = PROJECT_ROOT / ".env"
        if local_env.exists():
            self.assert_assignments_have_chinese_comments(
                local_env.read_text(encoding="utf-8").splitlines()
            )

    def test_local_env_deepseek_public_state_matches_when_present(self) -> None:
        local_env = PROJECT_ROOT / ".env"
        if not local_env.exists():
            return

        expected_local_deepseek_values = {
            "AGENT_LLM_DEEPSEEK_BASE_URL": "https://api.deepseek.com",
            "AGENT_LLM_DEEPSEEK_FAST_MODEL": "deepseek-v4-flash",
            "AGENT_LLM_DEEPSEEK_BALANCED_MODEL": "deepseek-v4-flash",
            "AGENT_LLM_DEEPSEEK_STRONG_MODEL": "deepseek-v4-pro",
            "AGENT_LLM_DEEPSEEK_API_KEY": "",
            "AGENT_LLM_MODEL_POOL_BASE_URL": "",
            "AGENT_LLM_MODEL_POOL_API_KEY": "",
        }
        values = self.read_env_values(local_env)

        for key, expected_value in expected_local_deepseek_values.items():
            if values.get(key) != expected_value:
                self.fail("本机 .env DeepSeek 公开状态不匹配")

    def test_deepseek_default_mapping_uses_current_official_model_ids(self) -> None:
        values = self.read_env_values(PROJECT_ROOT / ".env.example")

        self.assertEqual(values["AGENT_LLM_DEEPSEEK_BASE_URL"], "https://api.deepseek.com")
        self.assertEqual(values["AGENT_LLM_DEEPSEEK_API_KEY"], "")
        self.assertEqual(values["AGENT_LLM_DEEPSEEK_FAST_MODEL"], "deepseek-v4-flash")
        self.assertEqual(values["AGENT_LLM_DEEPSEEK_BALANCED_MODEL"], "deepseek-v4-flash")
        self.assertEqual(values["AGENT_LLM_DEEPSEEK_STRONG_MODEL"], "deepseek-v4-pro")

    def test_routing_template_declares_dynamic_deepseek_default(self) -> None:
        document = tomllib.loads(
            (PROJECT_ROOT / "config/llm-routing.toml").read_text(encoding="utf-8")
        )

        self.assertEqual(
            document["router"]["selection_mode"],
            "agent_proposed_with_harness_guardrails",
        )
        self.assertTrue(document["router"]["allow_lower_tier_degrade_on_retry"])
        self.assertTrue(document["providers"]["deepseek_direct"]["enabled"])
        self.assertEqual(
            document["providers"]["deepseek_direct"]["api_key_env"],
            "AGENT_LLM_DEEPSEEK_API_KEY",
        )
        self.assertEqual(
            document["routes"]["chat_default"]["selection_order"],
            "adaptive",
        )
        self.assertEqual(
            document["routes"]["chat_default"]["allowed_tiers"],
            ["fast", "balanced", "strong"],
        )

    def test_future_model_pool_is_reserved_but_disabled(self) -> None:
        document = tomllib.loads(
            (PROJECT_ROOT / "config/llm-routing.toml").read_text(encoding="utf-8")
        )

        pool = document["providers"]["model_pool"]
        self.assertFalse(pool["enabled"])
        self.assertEqual(pool["adapter_kind"], "unconfigured")
        self.assertEqual(pool["api_key_env"], "AGENT_LLM_MODEL_POOL_API_KEY")

    def test_env_template_contains_only_empty_runtime_values(self) -> None:
        values = self.read_env_values(PROJECT_ROOT / ".env.example")

        for key in (
            "AGENT_VECTOR_DATABASE_URL",
            "AGENT_TASK_BROKER_URL",
            "AGENT_RUN_EVENT_REDIS_URL",
            "AGENT_EMBEDDING_DASHSCOPE_BASE_URL",
            "AGENT_EMBEDDING_DASHSCOPE_API_KEY",
            "AGENT_EMBEDDING_MODEL",
            "AGENT_EMBEDDING_DIMENSIONS",
            "AGENT_RERANK_DASHSCOPE_API_KEY",
            "AGENT_COS_SECRET_ID",
            "AGENT_COS_SECRET_KEY",
            "AGENT_COS_REGION",
            "AGENT_COS_BUCKET",
            "AGENT_COS_BASE_URL",
            "AGENT_LLM_DEEPSEEK_API_KEY",
            "AGENT_LLM_MODEL_POOL_BASE_URL",
            "AGENT_LLM_MODEL_POOL_API_KEY",
        ):
            self.assertIn(key, values)
            self.assertEqual(values[key], "")

    def test_gitignore_keeps_local_env_out_of_version_control(self) -> None:
        content = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn(".env", content)
        self.assertIn(".env.*", content)
        self.assertIn("!.env.example", content)

    def test_gitignore_rules_have_adjacent_chinese_comments(self) -> None:
        self.assert_rules_have_chinese_comments(
            (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        )

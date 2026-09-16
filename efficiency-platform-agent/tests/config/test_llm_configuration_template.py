from __future__ import annotations

import tempfile
import tomllib
import unittest
from collections.abc import Iterable
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class LlmConfigurationTemplateTest(unittest.TestCase):
    @staticmethod
    def has_meaningful_chinese_comment(line: str) -> bool:
        chinese_character_count = sum(
            "\u4e00" <= character <= "\u9fff" for character in line
        )
        return (
            line.startswith("#")
            and chinese_character_count >= 8
            and any(punctuation in line for punctuation in ("。", "；"))
        )

    @staticmethod
    def assert_assignments_have_chinese_comments(lines: list[str]) -> None:
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue

            previous = lines[index - 1].strip() if index else ""
            if not LlmConfigurationTemplateTest.has_meaningful_chinese_comment(
                previous
            ):
                raise AssertionError(
                    f"配置项缺少紧邻的中文说明：{stripped.split('=', 1)[0]}"
                )

    @staticmethod
    def read_env_values(path: Path) -> dict[str, str]:
        return {
            key: value
            for line in path.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#") and "=" in line
            for key, value in [line.split("=", maxsplit=1)]
        }

    @staticmethod
    def read_env_keys(path: Path) -> set[str]:
        """只读取环境文件中的配置键名，不构造或保留配置值。"""
        return {
            line.split("=", maxsplit=1)[0]
            for line in path.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#") and "=" in line
        }

    @staticmethod
    def assert_local_env_configuration_structure(keys: Iterable[str]) -> None:
        """只校验本机配置项结构，不对任何本机配置值作断言。"""
        required_keys = (
            "AGENT_LLM_DEEPSEEK_BASE_URL",
            "AGENT_LLM_DEEPSEEK_FAST_MODEL",
            "AGENT_LLM_DEEPSEEK_BALANCED_MODEL",
            "AGENT_LLM_DEEPSEEK_STRONG_MODEL",
            "AGENT_LLM_DEEPSEEK_API_KEY",
            "AGENT_LLM_MODEL_POOL_BASE_URL",
            "AGENT_LLM_MODEL_POOL_API_KEY",
        )
        missing_keys = [key for key in required_keys if key not in keys]
        if missing_keys:
            raise AssertionError("本机 .env 配置结构缺少必要项")

    @staticmethod
    def assert_rules_have_chinese_comments(lines: list[str]) -> None:
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            previous = lines[index - 1].strip() if index else ""
            if not LlmConfigurationTemplateTest.has_meaningful_chinese_comment(
                previous
            ):
                raise AssertionError(f"忽略规则缺少紧邻的中文说明：{stripped}")

    def test_shared_configuration_assignments_have_chinese_comments(self) -> None:
        self.assert_assignments_have_chinese_comments(
            (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        )
        self.assert_assignments_have_chinese_comments(
            (PROJECT_ROOT / "config" / "llm-routing.toml")
            .read_text(encoding="utf-8")
            .splitlines()
        )

    def test_rejects_placeholder_chinese_comment_for_assignment(self) -> None:
        with self.assertRaises(AssertionError) as context:
            self.assert_assignments_have_chinese_comments(
                [
                    "# 中文",
                    "AGENT_LLM_DEEPSEEK_API_KEY=should-not-appear",
                ]
            )

        message = str(context.exception)
        self.assertIn("AGENT_LLM_DEEPSEEK_API_KEY", message)
        self.assertNotIn("should-not-appear", message)

    def test_local_env_assignments_have_chinese_comments_when_present(self) -> None:
        local_env = PROJECT_ROOT / ".env"
        if local_env.exists():
            self.assert_assignments_have_chinese_comments(
                local_env.read_text(encoding="utf-8").splitlines()
            )

    def test_local_env_values_are_not_compared(self) -> None:
        local_env = PROJECT_ROOT / ".env"
        if local_env.exists():
            self.assert_local_env_configuration_structure(self.read_env_keys(local_env))
            return

        values = {
            "AGENT_LLM_DEEPSEEK_BASE_URL": "arbitrary-local-url",
            "AGENT_LLM_DEEPSEEK_FAST_MODEL": "arbitrary-fast-model",
            "AGENT_LLM_DEEPSEEK_BALANCED_MODEL": "arbitrary-balanced-model",
            "AGENT_LLM_DEEPSEEK_STRONG_MODEL": "arbitrary-strong-model",
            "AGENT_LLM_DEEPSEEK_API_KEY": "opaque-configured-key",
            "AGENT_LLM_MODEL_POOL_BASE_URL": "arbitrary-pool-url",
            "AGENT_LLM_MODEL_POOL_API_KEY": "opaque-pool-key",
        }

        self.assert_local_env_configuration_structure(values)

    def test_present_local_env_missing_required_key_is_rejected(self) -> None:
        required_keys = (
            "AGENT_LLM_DEEPSEEK_BASE_URL",
            "AGENT_LLM_DEEPSEEK_FAST_MODEL",
            "AGENT_LLM_DEEPSEEK_BALANCED_MODEL",
            "AGENT_LLM_DEEPSEEK_STRONG_MODEL",
            "AGENT_LLM_DEEPSEEK_API_KEY",
            "AGENT_LLM_MODEL_POOL_BASE_URL",
            "AGENT_LLM_MODEL_POOL_API_KEY",
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            (temporary_root / ".env").write_text(
                "\n".join(f"{key}=" for key in required_keys[:-1]),
                encoding="utf-8",
            )

            with (
                patch(__name__ + ".PROJECT_ROOT", temporary_root),
                self.assertRaises(AssertionError),
            ):
                self.test_local_env_values_are_not_compared()

    def test_local_env_structure_does_not_read_values(self) -> None:
        local_env = PROJECT_ROOT / ".env"
        if local_env.exists():
            with patch.object(
                LlmConfigurationTemplateTest,
                "read_env_values",
                side_effect=AssertionError("不应读取本机配置值"),
            ):
                self.test_local_env_values_are_not_compared()

    def test_deepseek_default_mapping_uses_current_official_model_ids(self) -> None:
        values = self.read_env_values(PROJECT_ROOT / ".env.example")

        self.assertEqual(
            values["AGENT_LLM_DEEPSEEK_BASE_URL"], "https://api.deepseek.com"
        )
        self.assertEqual(values["AGENT_LLM_DEEPSEEK_API_KEY"], "")
        self.assertEqual(values["AGENT_LLM_DEEPSEEK_FAST_MODEL"], "deepseek-v4-flash")
        self.assertEqual(
            values["AGENT_LLM_DEEPSEEK_BALANCED_MODEL"], "deepseek-v4-flash"
        )
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

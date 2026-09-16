from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class LlmConfigurationTemplateTest(unittest.TestCase):
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
        lines = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        values = {
            key: value
            for line in lines
            if line and not line.startswith("#") and "=" in line
            for key, value in [line.split("=", maxsplit=1)]
        }

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
            "AGENT_LLM_DEEPSEEK_BASE_URL",
            "AGENT_LLM_DEEPSEEK_API_KEY",
            "AGENT_LLM_DEEPSEEK_FAST_MODEL",
            "AGENT_LLM_DEEPSEEK_BALANCED_MODEL",
            "AGENT_LLM_DEEPSEEK_STRONG_MODEL",
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

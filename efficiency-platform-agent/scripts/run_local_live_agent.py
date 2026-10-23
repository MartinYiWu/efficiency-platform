"""使用开发环境现有配置启动本地实时研究 Agent。"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import quote_plus

import uvicorn
import yaml
from pydantic import SecretStr

from efficiency_platform_agent.configuration.integration import (
    IntegrationGate,
    S7IntegrationSettings,
)
from efficiency_platform_agent.configuration.research import ResearchPipelineSettings
from efficiency_platform_agent.harness.local_real_factory import (
    build_local_agent_application,
)


def _spring_default(value: object) -> str:
    text = str(value)
    matched = re.fullmatch(r"\$\{[^:}]+:(.*)\}", text)
    return matched.group(1) if matched else text


def _runtime_database_url(root: Path) -> str:
    java_config = (
        root.parent
        / "ai-efficiency-platform"
        / "aiep-boot"
        / "src"
        / "main"
        / "resources"
        / "application.yml"
    )
    config = yaml.safe_load(java_config.read_text(encoding="utf-8"))
    datasource = config["spring"]["datasource"]
    jdbc_url = _spring_default(datasource["url"])
    host = jdbc_url.split("://", 1)[1].split("/", 1)[0]
    return (
        "mysql+asyncmy://"
        f"{quote_plus(_spring_default(datasource['username']))}:"
        f"{quote_plus(_spring_default(datasource['password']))}@{host}/"
        "ai_efficiency_platform_agent?charset=utf8mb4"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    base = S7IntegrationSettings.from_env_file(root / ".env")
    gates = dict(base.gates)
    gates[IntegrationGate.DEEPSEEK_WEB_SEARCH.value] = False
    settings = base.model_copy(
        update={
            "runtime_database_url": SecretStr(_runtime_database_url(root)),
            "gates": gates,
        }
    )
    research = ResearchPipelineSettings(
        intent_pipeline_version="intent-v2",
        research_pipeline_version="research-v2",
        runtime_mode="local_live",
        research_replan_enabled=True,
        research_decision_mode="model",
        research_source_allowlist=(
            "google_blog_rss",
            "langgraph_releases_atom",
            "hacker_news_api",
            "openai_news_rss",
            "huggingface_blog_rss",
        ),
        research_policy_version="research-policy/local-live-v2",
        state_backend="memory",
        rollout_mode="tenant_allowlist",
        rollout_tenant_allowlist=("dev", "acceptance-tenant"),
    )
    bundle = build_local_agent_application(
        settings=settings,
        research_v2_settings=research,
    )
    uvicorn.run(
        bundle.app,
        host="127.0.0.1",
        port=args.port,
        log_level="info",
        loop=(
            "efficiency_platform_agent.main:selector_loop_factory"
            if sys.platform == "win32"
            else "auto"
        ),
    )


if __name__ == "__main__":
    main()

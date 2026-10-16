"""把版本化 Prompt 初始资产安装到配置的 Agent MySQL。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from efficiency_platform_agent.configuration.integration import S7IntegrationSettings
from efficiency_platform_agent.persistence.mysql_runtime import MySqlRuntimeDatabase
from efficiency_platform_agent.prompts.installer import install_prompt_seed
from efficiency_platform_agent.prompts.seeds import build_operation_prompt_seed


async def main() -> None:
    root = Path(__file__).resolve().parents[1]
    settings = S7IntegrationSettings.from_env_file(root / ".env")
    if settings.runtime_database_url is None:
        raise RuntimeError("AGENT_RUNTIME_DATABASE_URL_MISSING")
    database = MySqlRuntimeDatabase(
        settings.runtime_database_url.get_secret_value()
    )
    try:
        seed = build_operation_prompt_seed()
        await install_prompt_seed(database.engine, seed)
        print(
            "prompt_assets_installed "
            f"definitions={len(seed.definitions)} versions={len(seed.versions)} "
            f"releases={len(seed.releases)}"
        )
    finally:
        await database.close()


if __name__ == "__main__":
    asyncio.run(main())

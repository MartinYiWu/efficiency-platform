"""客服无检索分支/HR真实服务与发布仓储；仅供应商模型边界使用Fake。"""

from __future__ import annotations

import asyncio
import json
import re
import socket
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

import httpx
import uvicorn
from fastapi import FastAPI
from sqlalchemy import text

from efficiency_platform_agent.agents.customer_service.graph import CustomerServiceGraph
from efficiency_platform_agent.agents.customer_service.model_gateway import (
    ReleaseStructuredModelGateway,
    _freeze,
)
from efficiency_platform_agent.agents.customer_service.release_bundle import (
    CustomerServiceReleaseBundle,
)
from efficiency_platform_agent.agents.customer_service.release_repository import (
    MySqlReleaseRepository,
)
from efficiency_platform_agent.agents.customer_service.service import (
    CustomerServiceRunService,
)
from efficiency_platform_agent.agents.customer_service.state import (
    CustomerServiceAnswer,
    IntentDecision,
)
from efficiency_platform_agent.agents.hr.service import HrSkillService
from efficiency_platform_agent.api.customer_service_routes import (
    build_customer_service_router,
)
from efficiency_platform_agent.api.hr_skill_routes import (
    HrSkillEndpoint,
    build_hr_skill_router,
)
from efficiency_platform_agent.context.controller import ContextController
from efficiency_platform_agent.context.dispatch import (
    ContextDispatch,
    ControlledModelProvider,
)
from efficiency_platform_agent.contracts.hr import JdOutput
from efficiency_platform_agent.core.context_control import ModelCapacity, WindowLimits
from efficiency_platform_agent.core.context_dispatch import current_model_stage
from efficiency_platform_agent.core.context_ports import ContextMetadata
from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderMessage,
    ProviderResult,
    ProviderUsage,
)
from efficiency_platform_agent.harness.context_authority import ServerDispatchAuthority
from efficiency_platform_agent.harness.hr_factory import (
    HrPolicyModelProvider,
    PersistentHrRunControlStore,
    internal_hr_authorizer,
)
from efficiency_platform_agent.persistence.context_manifest import (
    MySqlContextManifestStore,
)
from efficiency_platform_agent.persistence.context_stage import MySqlContextStageStore
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger
from efficiency_platform_agent.prompts.mysql_repository import (
    MySqlPromptRepository,
    _checksum,
)
from efficiency_platform_agent.prompts.runtime import PromptAssembler
from efficiency_platform_agent.providers.llm.fake import FakeModelProvider
from efficiency_platform_agent.providers.llm.request_counter import (
    ConservativeRequestTokenCounter,
)
from tests.api.test_customer_service_release_routes import _payload, _rechecksum

MODEL = "synthetic-business"
PROVIDER = "deepseek"
RELEASE = UUID("b0900000-0000-0000-0000-000000000001")
SECRET = "memory-business-it-internal-only-000000"
KEY = b"memory-business-it-hmac-only-000000000"
ROOT = Path(__file__).resolve().parents[3]


class BusinessBoundaryProvider(FakeModelProvider):
    def __init__(self):
        super().__init__("synthetic-business-boundary", [])
        self.requests = []
        self.calls = Counter()
        self.unknown = False

    async def complete(self, request):
        stage = current_model_stage()
        assert stage is not None
        node = stage.node_id
        self.calls[node] += 1
        self.requests.append(request)
        if self.unknown:
            raise ValueError("PROVIDER_TRANSPORT_LOST")
        if (
            node in {"customer-service:intent", "hr:hr.jd.draft"}
            and self.calls[node] < 3
        ):
            content = "{}"
        elif node == "customer-service:intent":
            content = json.dumps(
                {
                    "intent_type": "GENERAL_QUERY",
                    "requires_company_knowledge": False,
                    "requires_general_advice": True,
                    "normalized_question": "合成一般建议",
                }
            )
        elif node == "customer-service:answer_general":
            content = json.dumps(
                {
                    "contract_version": "customer-service-answer/1",
                    "answer_mode": "GENERAL_ADVICE",
                    "general_advice": {"paragraphs": ["合成一般建议"]},
                }
            )
        elif node == "hr:hr.jd.draft":
            content = '{"candidates":[]}'
        else:
            raise AssertionError("未发布的合成供应商节点")
        return ProviderResult(
            request.contract_version,
            ProviderMessage("assistant", content),
            ProviderUsage(1, 1, 0, 0, 1),
        )


def release_bundle():
    # 复用既有Release合成资产规则；实际读取/冻结仍经过MySqlReleaseRepository。
    value = _payload()
    value["model_policy"].update(
        provider=PROVIDER,
        model_name=MODEL,
        max_input_tokens=131072,
        max_output_tokens=1024,
        temperature=0.0,
        max_retries=2,
    )
    identity = value["prompt_bindings"][0]
    bindings = [identity]
    for stage in ("intent", "answer_general"):
        bindings.append(
            {
                "stage_key": stage,
                "ordinal": 1,
                "prompt_key": "synthetic." + stage,
                "prompt_version": "1.0.0",
                "checksum": "a" * 64,
                "messages": [
                    {
                        "ordinal": 1,
                        "role": "USER",
                        "message_key": stage,
                        "content_template": "{{input_json}}",
                        "content_format": "JSON",
                        "trusted_instruction": False,
                        "checksum": "b" * 64,
                        "variables": [],
                    }
                ],
            }
        )
    value["prompt_bindings"] = sorted(
        bindings, key=lambda item: (item["stage_key"], item["ordinal"])
    )
    _rechecksum(value)
    return CustomerServiceReleaseBundle.model_validate(value)


def published_metadata():
    capacity = ModelCapacity(
        PROVIDER,
        MODEL,
        "synthetic/1",
        200000,
        131072,
        1024,
        "conservative-utf8/1",
        "openai-chat/1",
        "NO_REASONING",
        True,
        "synthetic-not-real-capacity",
    )
    limits = WindowLimits(200000, 131072, 1024, 4096, 120000)
    published = {}
    for node, schema, thinking in (
        ("customer-service:intent", IntentDecision, False),
        ("customer-service:answer_general", CustomerServiceAnswer, True),
    ):
        options = (
            ("logical_model", MODEL),
            ("temperature", 0.0),
            ("top_p", 0.9),
            ("max_tokens", 1024),
            ("response_format", JsonObject((("type", "json_object"),))),
            ("json_schema", _freeze(schema.model_json_schema())),
        )
        if thinking:
            options += (("thinking", JsonObject((("type", "disabled"),))),)
        published[(PROVIDER, MODEL, node)] = ContextMetadata(
            node, "1", "1", "1", "1", 1, capacity, limits, JsonObject(options)
        )
    node = "hr:hr.jd.draft"
    options = JsonObject(
        (
            ("logical_model", MODEL),
            ("temperature", 0.0),
            ("max_tokens", 1024),
            ("response_format", JsonObject((("type", "json_object"),))),
        )
    )
    published[(PROVIDER, MODEL, node)] = ContextMetadata(
        node, "1", "1", "1", "1", 1, capacity, limits, options
    )
    return published


async def install_business_assets(engine):
    assert re.fullmatch(
        r"aiep_memory_it_[0-9]{8}_[0-9a-f]{10}", engine.url.database or ""
    )
    files = (
        ("20261015_001_Agent运行态MySQL", {"agent_run"}),
        (
            "20261016_001_Prompt资产多角色装配",
            {
                "agent_model_policy",
                "agent_output_contract",
                "agent_prompt_definition",
                "agent_prompt_version",
                "agent_prompt_message_template",
                "agent_prompt_variable",
                "agent_prompt_release",
                "agent_run_prompt_snapshot",
            },
        ),
        ("20261020_001_智能客服运行态MySQL", {"agent_release_bundle"}),
    )
    async with engine.begin() as connection:
        for topic, names in files:
            source = (ROOT / "sql/changes" / topic / "02-up.sql").read_text(
                encoding="utf-8"
            )
            source = re.sub(r"--[^\n]*", "", source)
            found = set()
            for statement in source.split(";"):
                match = re.match(r"\s*CREATE TABLE (\w+)\s*\(", statement)
                if match and match[1] in names:
                    await connection.execute(text(statement))
                    found.add(match[1])
            assert found == names
        # 合成发布资产使用生产checksum规则和真实JSON列，不接触共享发布配置。
        await connection.execute(
            text(
                "INSERT INTO agent_model_policy VALUES (1,'synthetic-hr','1.0.0','deepseek',:model,0,NULL,131072,1024,1000,30000,2,0,1,:checksum,0)"
            ),
            {
                "model": MODEL,
                "checksum": _checksum({"key": "synthetic-hr", "version": "1.0.0"}),
            },
        )
        schema = JdOutput.model_json_schema()
        await connection.execute(
            text(
                "INSERT INTO agent_output_contract VALUES (1,'synthetic-jd','1.0.0',CAST(:schema AS JSON),'synthetic',:checksum,1,0)"
            ),
            {"schema": json.dumps(schema), "checksum": _checksum(schema)},
        )
        await connection.execute(
            text(
                "INSERT INTO agent_prompt_definition VALUES (1,'hr.jd.draft','hr','draft',NULL,'synthetic','synthetic',1,0,0)"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO agent_prompt_version VALUES (1,1,'1.0.0','released',1,1,:checksum,'synthetic','synthetic',0,0,NULL)"
            ),
            {"checksum": _checksum({"prompt_key": "hr.jd.draft", "version": "1.0.0"})},
        )
        template = "{{ input_json }}"
        await connection.execute(
            text(
                "INSERT INTO agent_prompt_message_template VALUES (1,1,1,'user','input',:template,'json',0,:checksum)"
            ),
            {
                "template": template,
                "checksum": _checksum({"role": "user", "content": template}),
            },
        )
        await connection.execute(
            text(
                "INSERT INTO agent_prompt_variable VALUES (1,1,'input_json','json','user_input',1,1,100000,1)"
            )
        )
        await connection.execute(
            text("INSERT INTO agent_prompt_release VALUES (1,'dev',1,1,'synthetic',0)")
        )
    await MySqlReleaseRepository(engine).save(RELEASE, release_bundle())


async def seed_hr_run(engine, run, tenant):
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO agent_run VALUES (:run,:tenant,:run,'running',1,CAST('{}' AS JSON),0,0)"
            ),
            {"run": run, "tenant": tenant},
        )


@asynccontextmanager
async def running_business_app(engine, temp_path):
    await install_business_assets(engine)
    store = MySqlContextManifestStore(engine)
    authority = ServerDispatchAuthority(
        published_metadata(),
        {
            "customer-service:intent": ("customer-service", "intent"),
            "customer-service:answer_general": ("customer-service", "answer"),
            "hr:hr.jd.draft": ("hr.jd.draft", "draft"),
        },
    )
    authority.assert_ready()
    dispatch = ContextDispatch(
        ContextController(ConservativeRequestTokenCounter(), store, KEY),
        store,
        authority,
        stage_store=MySqlContextStageStore(engine, KEY),
        hmac_key=KEY,
    )
    boundary = BusinessBoundaryProvider()
    controlled = ControlledModelProvider(
        boundary, dispatch, PROVIDER, MODEL, paid_transport=False
    )
    # GENERAL_QUERY不进入检索；不以Fake检索/PG仓储伪称检索链已验收。
    customer = CustomerServiceRunService(
        CustomerServiceGraph(None),
        MySqlReleaseRepository(engine),
        lambda bundle: ReleaseStructuredModelGateway(controlled, bundle),
    )
    prompts = MySqlPromptRepository(engine)
    assembler = PromptAssembler(prompts, environment="dev")
    controls = PersistentHrRunControlStore(
        SqlitePaidBudgetLedger(temp_path / "fake-hr-control.sqlite3")
    )
    hr = HrSkillEndpoint(
        HrSkillService(assembler, HrPolicyModelProvider({MODEL: controlled})), controls
    )
    authorize = internal_hr_authorizer(SECRET)
    app = FastAPI()
    app.include_router(build_customer_service_router(customer, authorize))
    app.include_router(build_hr_skill_router(hr, authorize))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    listener.setblocking(False)
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", lifespan="off"))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if task.done():
                    await task
                    raise RuntimeError("合成HTTP fixture启动失败")
                await asyncio.sleep(0.01)
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{listener.getsockname()[1]}",
            timeout=30,
            trust_env=False,
        ) as client:
            yield client, boundary
    finally:
        server.should_exit = True
        try:
            async with asyncio.timeout(10):
                await task
        finally:
            if not task.done():
                task.cancel()
            listener.close()
            for run in customer._runs.values():
                if run.task is not None and not run.task.done():
                    run.task.cancel()
            await controls.close()

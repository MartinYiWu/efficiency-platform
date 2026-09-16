# Agent 侧技术组件选型

| 属性 | 内容 |
|---|---|
| 标题 | Agent 侧技术组件选型 |
| 状态 | 已批准 |
| 作者/负责人 | Agent 平台架构负责人 |
| 创建日期 | 2026-09-01 |
| 最后更新日期 | 2026-09-02 |
| 评审人/批准人 | 项目负责人（用户）；批准日期：2026-09-02；批准范围：P0～P5 技术组件及跨阶段一致性；评审结论：局部基线和总体组件基线通过；证据：本次任务完成逐项确认并明确回复“确认” |
| 关联 ADR/设计/计划 | [Agent 侧 P0～P5 总体技术架构设计](../superpowers/specs/2026-09-02-Agent侧P0-P5总体技术架构-设计.md)、[纯 Agent 侧总体架构](纯Agent侧总体架构.md)、[P1 Agent Runtime 技术组件选型设计](../superpowers/specs/2026-09-02-P1-Agent-Runtime技术组件选型-设计.md)、[P2 Provider 与 RAG 技术组件选型设计](../superpowers/specs/2026-09-02-P2-Provider与RAG技术组件选型-设计.md)、[P3 文档解析与 OCR 技术组件选型](../superpowers/specs/2026-09-02-P3-文档解析与OCR-技术选型.md)、[P4 公共研究与数据分析技术组件选型](../superpowers/specs/2026-09-02-P4-公共研究与数据分析-技术选型.md)、[P5 MCP、评测与基础质量保障技术组件选型](../superpowers/specs/2026-09-02-P5-MCP评测与基础质量保障-技术选型.md)、[P1 Agent Runtime 实施计划](../superpowers/plans/2026-09-02-P1-Agent-Runtime实施计划.md)、[Agent 侧架构骨架实施计划](../superpowers/plans/2026-09-01-Agent侧架构骨架-实施计划.md) |
| 替代关系 | 无 |
| 适用范围 | 纯 Agent 侧已批准技术组件与未来引入顺序；不表示组件已安装、接入或运行验证 |

> 基线日期：2026-09-02。本文只裁决纯 Agent 侧技术组件，不设计 Java 侧，也不讨论部署拓扑。具体补丁版本由首次兼容性 PoC 后写入 `uv.lock`，不在组件讨论阶段盲目锁死。

## 1. 总体结论

P0～P5 已逐项批准的技术栈如下；跨阶段总体一致性、正式实施与真实接入仍需后续可审计评审、PoC 和实施证据：

```text
Python 3.13 + uv + uv_build
FastAPI + Uvicorn + Pydantic v2 + pydantic-settings + HTTPX
LangGraph OSS 1.x StateGraph（唯一 Graph Runtime）
Taskiq + taskiq-redis RedisStreamBroker（异步执行，Windows/Python 3.13 PoC 门禁）
Redis Streams（任务 Broker、短期 Run Event、取消信号；Key 空间隔离）
PostgreSQL + Psycopg 3 + SQLAlchemy 2 async + Alembic
langgraph-checkpoint-postgres AsyncPostgresSaver
现有 pgvector + text-embedding-v4/1024 + qwen3-rerank + PostgreSQL 原生 FTS
OpenAI Python SDK + HTTPX Provider Adapters + cos-python-sdk-v5 + Jinja2
Docling 2.x + pypdfium2 5.x + PaddleOCR 3.x/PaddlePaddle 3.x
Agent Document AST + 结构优先切片 + semantic-text-splitter 0.32.x（仅超长叶节点）
DeepSeek Responses API server-side web_search + JSON Schema（复用 P2 Provider）
Polars 1.x + fastexcel/calamine（只读 XLSX）
MCP Python SDK 2.x
structlog + stdlib logging（P1）；OpenTelemetry/Prometheus/监控平台后置
pytest + pytest-asyncio + pytest-cov + respx + Hypothesis + Ruff + mypy
Pydantic 评测契约 + JSONL/Parquet 回归集 + Polars 聚合 + 项目内确定性指标
uv audit --frozen（复用现有 uv）
```

## 2. 基础运行时选型

| 技术域 | 选型 | 裁决理由 | 费用属性 |
|---|---|---|---|
| 语言 | CPython 3.13.x | 作为 P0 项目基线；系统 3.11.9 保留作为回退，项目已使用 uv 托管的 3.13.15 建立隔离环境并完成骨架验证 | 免费 |
| 项目与依赖 | uv + `pyproject.toml` + `.python-version` + `.venv` + `uv.lock` | uv 统一管理 Python 版本、虚拟环境、依赖解析和跨平台锁文件；不向系统 Python 安装项目依赖 | 免费开源 |
| 构建后端 | `uv_build` | 当前是纯 Python 标准 `src/` 布局，不需要 Hatchling、Setuptools 的额外构建能力 | 免费开源 |
| API | FastAPI 0.135.0+ + Uvicorn | 异步 API、OpenAPI、Pydantic 集成和原生 SSE；通过 `EventSourceResponse` 输出带事件 ID、续传和 keep-alive 的运行事件 | 免费开源 |
| Schema | Pydantic v2 + pydantic-settings | 所有请求、事件、工具参数、Provider 配置的统一校验 | 免费开源 |
| HTTP Client | HTTPX | 异步、连接池、超时、流式响应；作为厂商 API 和外部 Tool 的基础客户端 | 免费开源 |
| 序列化 | stdlib JSON | P0 保持单一标准实现；`orjson` 只有在真实性能证据出现后才重新评估 | 免费开源 |

FastAPI 0.135.0 起原生提供 SSE、事件 ID、`Last-Event-ID` 续传和 keep-alive，适合 Agent Token、Step、Tool、Approval 等事件流：[FastAPI SSE](https://fastapi.tiangolo.com/tutorial/server-sent-events/)。uv 官方提供 Python 版本、项目环境和跨平台锁文件管理：[uv Projects](https://docs.astral.sh/uv/concepts/projects/)。纯 Python `src/` 项目使用其原生构建后端：[uv build backend](https://docs.astral.sh/uv/configuration/build-backend/)。

### 2.1 P0 已确认基线

2026-09-02 的组件讨论已确认以下 P0 基线；它表示技术方向已确认，不表示依赖已经安装或兼容性已经验收：

```text
系统 Python：保留 CPython 3.11.9
项目 Python：uv 托管 CPython 3.13.15
环境与依赖：uv + 项目独立 .venv + uv.lock
构建：uv_build
API：FastAPI + Uvicorn
Schema 与配置：Pydantic v2 + pydantic-settings
HTTP Client：HTTPX
测试：pytest + pytest-asyncio + pytest-cov + respx
格式化与 Lint：Ruff
类型检查：mypy
```

运行依赖、开发依赖和构建依赖 MUST 分组管理：

```text
运行依赖：fastapi、uvicorn、pydantic、pydantic-settings、httpx
开发依赖：pytest、pytest-asyncio、pytest-cov、respx、ruff、mypy
构建依赖：uv_build
```

P0 的框架边界固定为：

```text
api/                 MAY 使用 FastAPI 与 Pydantic
providers/、tools/   MAY 使用 HTTPX 与边界 Pydantic Adapter
core/                MUST 保持纯 Python，MUST NOT 依赖 FastAPI、Pydantic、HTTPX
```

直接依赖使用经 PoC 验证的兼容版本范围，直接和传递依赖的精确解析结果写入 `uv.lock`。`uv.lock` MUST 纳入版本管理且 MUST NOT 手工修改。P0 实施验收 MUST 在 Python 3.13 下重新执行格式、Lint、类型检查和全量测试。

当前环境证据（2026-09-02）：

```text
uv：0.12.9
系统解释器：CPython 3.11.9，保持不变
项目解释器：CPython 3.13.15，64bit AMD64
项目解释器路径：.venv/Scripts/python.exe
.python-version：3.13
requires-python：>=3.13,<3.14
uv.lock：已生成
Python 3.13 骨架测试：39/39 PASS，0 failures，0 errors，0 skipped
P0 API/质量依赖：尚未安装
P1 Agent Runtime 依赖：尚未安装
```

## 3. Agent 编排与多 Agent

| 技术域 | 选型 | 使用方式 |
|---|---|---|
| Graph Runtime | LangGraph OSS 1.x | 唯一编排运行时，不并存第二套 Agent 框架 |
| Harness | 自研薄 Harness，构建在 LangGraph 外层 | 负责身份、权限、预算、超时、取消、审计边界、关联标识和错误；完整 Trace 后置，不使用重型黑盒 Harness |
| Direct | 普通函数/单节点 Graph | 低复杂度请求不进入循环 |
| Workflow | LangGraph 确定性 Graph | 固定步骤、审批和强审计流程 |
| ReAct | LangGraph 有界循环 | 限定工具白名单、最大步数、Token 和时间预算 |
| Plan-and-Execute | Planner/Executor/Replanner 子图 | 长任务的计划可持久化、暂停和恢复 |
| Multi-Agent | 自定义 Supervisor Graph + Specialist Subgraphs | 中央调度、上下文隔离、结构化汇总；禁止专家 Agent 自由互聊 |
| Checkpoint | `langgraph-checkpoint-postgres` | 统一使用 PostgreSQL 持久化，禁止生产态内存 Checkpointer |

LangGraph 官方定位就是低层编排运行时，提供持久执行、流式、人机协同和持久化：[LangGraph Overview](https://docs.langchain.com/oss/python/langgraph/overview)。其 Checkpoint 支持失败恢复、记忆和 human-in-the-loop：[Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)。官方 Subagent 模式也是中央 Supervisor 调用子 Agent，并支持并行和上下文隔离：[Subagents](https://docs.langchain.com/oss/python/langchain/multi-agent/subagents)。

### 不选择的框架

| 不选项 | 原因 |
|---|---|
| AutoGen / CrewAI | 会引入另一套 Agent 对话和编排语义，不符合中央 Supervisor 与统一 Graph Runtime |
| LlamaIndex Workflow | RAG 能力可借鉴，但不作为第二编排内核 |
| Dify / Coze 类平台 | 适合低代码应用，不适合作为本项目可测试、可治理的底层运行时 |
| Deep Agents 直接做总框架 | 可参考其 Harness 思想，但当前需要更稳定的内部契约和更小黑盒面 |
| 完整 LangChain 作为基础框架 | 不选；只接受 LangGraph 所需 `langchain-core` 基础能力。未来 `langchain.create_agent` 只能按 Specialist 单独评估并作为 Harness 管控的子图 |
| Temporal | 当前 LangGraph Checkpoint + Taskiq + PostgreSQL Outbox 足够；只有出现跨天、跨服务强补偿事务需求时再评估 |
| 去中心化 Swarm | 权限、成本、终止和问题定位不可控 |

## 4. 异步任务与调度

| 组件 | 裁决 |
|---|---|
| Taskiq + taskiq-redis | 使用 `RedisStreamBroker` 处理长任务分发、Worker 并发、消息 ACK 和失败重投递；Windows + Python 3.13 PoC 是强制准入门禁 |
| 现有 Redis | 隔离承载 Taskiq Broker、短期 Run Event Streams、取消快信号、限流、锁和缓存；不保存权威状态 |
| PostgreSQL Outbox | Run、状态事件与 Dispatch Outbox 在同一事务写入，由 Dispatcher 至少一次投递到 Taskiq |
| PostgreSQL Run 状态 | Worker 通过 `run_id + state_version` 条件认领，保证重复消息只产生一次有效执行 |
| 周期调度 | P1 不引入；真实周期任务需求出现后单独选型 |

职责必须分开：LangGraph 管“任务内部如何执行及从哪里恢复”，Taskiq 管“任务何时被哪个 Worker 执行”，PostgreSQL 管权威状态与可靠投递事实。Taskiq 的 PyPI 元数据包含 Windows 无关的 OS 声明和 Python 3.13 分类，但开发状态仍标注 Alpha，故不能跳过 PoC：[Taskiq](https://pypi.org/project/taskiq/)。`taskiq-redis` 提供带 ACK 的 `RedisStreamBroker`：[taskiq-redis](https://pypi.org/project/taskiq-redis/)。Celery 不作为本项目候选，因为其官方文档明确不支持 Microsoft Windows：[Celery 平台支持](https://docs.celeryq.dev/en/stable/getting-started/introduction.html)。

## 5. 模型调用与结构化输出

> **后续裁决。** 本节关于 LLM 来源、静态模型路由和降级的表述，已由[ADR-0001 自适应模型策略路由](../adr/ADR-0001-自适应模型策略路由.md)部分替代。Embedding、Rerank、结构化输出、Prompt 与其他 P2 裁决保持有效。

| 能力 | 选型 | 说明 |
|---|---|---|
| Chat/Reasoning | 复用现有 AIHub/DeepSeek 配置 | `deepseek-v4-pro` 作为主模型逻辑名，`deepseek-v4-flash` 作为快速/低成本逻辑名；保留现有 `deepseek-chat` Provider |
| 通用模型客户端 | OpenAI Python SDK | 用于 OpenAI-compatible Chat/Embedding 端点 |
| 特殊厂商接口 | HTTPX Adapter | DashScope Rerank 等非统一接口独立适配；云 OCR 仅保留默认关闭的未来可选端口 |
| 结构化输出 | Pydantic Schema + Provider JSON Schema 能力 | 先校验后进入 Graph State，禁止把原始自由文本当控制指令 |
| Prompt | Jinja2 `ImmutableSandboxedEnvironment` + `StrictUndefined` + Agent 自有类型化消息契约 | 只渲染受控版本模板；外部内容仅作为变量数据；Prompt 发布、灰度和回滚属于 Agent 侧持久化能力 |
| 模型路由 | 内部 Model Router | 按能力、延迟、预算、租户策略和失败降级选择 Provider |

不引入 LiteLLM Proxy。当前已有模型入口且 Provider 端口已经隔离厂商差异，再增加代理会扩大配置、故障和观测链路。以后模型供应商明显增多时，可在不改上层契约的前提下重新评估。

## 6. RAG、向量与重排

### 6.1 直接复用

| 已存在能力 | 当前核验结果 | Agent 侧裁决 |
|---|---|---|
| Embedding | DashScope `text-embedding-v4`，1024 维 | 直接复用模型、密钥和 1024 维配置 |
| Vector DB | PostgreSQL + pgvector | 直接复用连接；Agent 通过 Psycopg 3 / pgvector-python 访问 |
| Vector Index | HNSW + COSINE_DISTANCE | 保持现有索引和距离度量，不重建向量空间 |
| 召回 | 现有默认 `hybrid`，向量与关键词候选融合 | 延续混合检索，不另引 Elasticsearch/OpenSearch |
| Cache | Redis | 复用连接，增加 Agent 命名空间隔离 |
| Artifact | Tencent COS | 复用配置，通过 `cos-python-sdk-v5` Provider 适配 |
| LLM | AIHub/DeepSeek | 复用模型入口和密钥，不复制明文秘钥到仓库 |

P2 关键词检索固定使用 PostgreSQL 原生 FTS；`pg_trgm` 已从必选降为可选。2026-09-02 对当前目标 PostgreSQL 的只读检查显示 `pg_trgm` 不可用且未安装，因此 P2 不依赖该扩展，也不执行任何扩展或索引 DDL。中文 FTS 质量必须在后续脱敏语料 PoC 中验证。

阿里云官方说明 `text-embedding-v4` 支持 64～2048 维且默认 1024，和现有索引一致：[Embedding and Rerank](https://help.aliyun.com/zh/model-studio/embedding-rerank-model)。因此：

- 现有索引继续固定 `text-embedding-v4 + 1024 + cosine`；
- 不用另一 Embedding 模型直接查询同一向量索引；
- 模型或维度升级必须创建新索引版本并做双写/回放/A-B 验证；
- 本阶段不执行任何数据库 DDL。

### 6.2 新增重排

主选阿里云 `qwen3-rerank`，Provider 的实际模型 ID 配置化。控制台中的 `qwen3.7-text-rerank` 可作为候选模型做一次真实 API 冒烟与质量 A/B，通过后替换配置，不能仅凭控制台展示名写死代码。

推荐检索链：

```text
Query Rewrite
  → pgvector Top-K + PostgreSQL 全文/关键词 Top-K
  → RRF/加权融合
  → qwen3-rerank 重排
  → Context Budget Packer
  → Evidence/Citation Assembly
```

## 7. 文档解析与 OCR

| 层级 | 组件 | 处理范围 | 费用属性 |
|---|---|---|---|
| 文件识别 | `puremagic 2.x` + `mimetypes` | 文件签名为主，与扩展名、MIME 和允许清单交叉验证 | 免费开源/标准库 |
| 解析前安全 | `zipfile`、`pypdf`、Pillow、`defusedxml`、`nh3` | 容器、PDF、图片、XML、HTML 的资源与主动内容边界 | 免费开源/标准库 |
| 文本编码 | `charset-normalizer 3.x` | TXT、Markdown、CSV、HTML 统一规范为 UTF-8 | 免费开源 |
| 主文档解析 | Docling 2.x | PDF、DOCX、XLSX、PPTX、TXT、Markdown、CSV、HTML | 免费开源，自付算力 |
| PDF 页面渲染 | `pypdfium2 5.x` | 只栅格化扫描 PDF 或混合 PDF 中需要 OCR 的页面 | 免费开源，自付算力 |
| 本地 OCR 主路径 | PaddleOCR 3.x + PaddlePaddle 3.x | 图片和扫描页的中英文文本识别 | 免费开源，自付 CPU/GPU |
| 复杂版面/表格 | PP-StructureV3 | 仅在复杂布局或表格路由命中时启用，不默认打开公式、印章和图表专项模块 | PaddleOCR 同一生态，无 API 调用费 |
| 标准文档契约 | Pydantic v2 Agent `Document AST` | 版本化 JSON 权威结果；Markdown、纯文本和 Chunk 均为派生物 | Agent 自有契约 |
| 文档切片 | Agent 结构优先切片 + `semantic-text-splitter 0.32.x` | 先按标题、段落、列表、表格和来源边界切片；第三方切分器只处理超长纯文本叶节点 | 免费开源/自研 |
| 云 OCR 接口 | 阿里云 `qwen3.5-ocr` Adapter Port | 仅保留未来可选接口；默认关闭，无可接受免费额度时不得启用 | 当前不产生费用，不属于活动链路 |

处理链固定为：

```text
puremagic/扩展名/MIME + 文件安全预检
  → charset-normalizer（轻量文本）
  → Docling 主解析
  → 扫描/混合 PDF 的目标页经 pypdfium2 栅格化
  → PaddleOCR 本地识别
  → 复杂布局/表格按需进入 PP-StructureV3
  → Agent Document AST + 来源页码/坐标/解析版本
  → 确定性质量门禁
  → 结构优先切片
  → P2 Embedding + pgvector + PostgreSQL FTS
```

质量状态统一为 `ACCEPTED`、`ACCEPTED_WITH_WARNINGS`、`REVIEW_REQUIRED`、`REJECTED`。质量由可复现规则裁决，不用 LLM 猜测缺失视觉内容。阿里云 OCR 不作为本地失败后的自动兜底，不参与当前验收；未来启用必须同时满足免费额度、数据合规和单独批准，免费额度用尽即停止，禁止自动转按量付费。

当前支持 PDF（文本、扫描、混合）、DOCX、XLSX、PPTX、TXT、Markdown、CSV、HTML、PNG、JPEG、TIFF、WebP。DOC/XLS/PPT、邮件、归档、EPUB、RTF、音频和视频暂缓。完整裁决、路由、安全、AST、质量和切片边界见[P3 文档解析与 OCR 技术组件选型](../superpowers/specs/2026-09-02-P3-文档解析与OCR-技术选型.md)。Docling 的统一表示和格式能力见[Docling 支持格式](https://docling-project.github.io/docling/usage/supported_formats/)，复杂版面能力见[PP-StructureV3](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PP-StructureV3.html)。

## 8. 公共互联网研究

| 能力 | 选型 | 约束 |
|---|---|---|
| 搜索发现与信息处理 | DeepSeek Responses API 服务端 `web_search_2025_08_26`（兼容 `web_search`） | 复用 P2 ModelProviderPort；要求可复核来源 URL，不自建搜索、爬虫或浏览器服务 |
| 结构化输出 | Provider `json_schema` + Pydantic v2 | 输出校验通过后才能进入 Graph State |
| Prompt | P2 Jinja2 安全模板 | 明确研究目标、时间窗、来源要求和输出 Schema |
| 来源证据 | 版本化 Pydantic 契约 | 标题、发布者、URL、发布时间、检索时间和所支持结论必须可关联 |
| 轻量去重 | URL 规范化 + 标准库哈希 | 只处理 Provider 返回结果，不抓取网页正文 |
| 运行与费用事实 | P1 Run/Step/Invocation/Usage | 记录模型、Prompt 版本、耗时与真实 Token |

现有企业 AIHub/DeepSeek endpoint 必须在后续获批 PoC 中证明同时支持 `/responses`、`web_search_2025_08_26`、`json_schema` 和可复核来源；适配器同时兼容正文中明确出现的 HTTPS 来源 URL，但不访问 URL；否则能力失败关闭，不用普通 Chat 响应伪装联网搜索。DeepSeek 官方当前声明 Responses API 支持服务端 `web_search` 和 JSON Schema：[Responses API](https://api-docs.deepseek.com/api/create-response/)。这里的“全网搜索”只表示 Provider 可覆盖的公共互联网范围，不承诺全量索引或穷尽检索。

当前不主动打开或下载模型返回的 URL，因此不引入 HTTP 抓取链。如果未来需要验证或抓取页面，必须重新评审并复用统一 SSRF Policy、版权和站点条款边界。任何收费商业热点、舆情、新闻或搜索数据源均不接入；若 DeepSeek `web_search` 存在独立搜索附加费用，则关闭该能力，不自动转用其他付费来源。

## 9. 数据分析能力

| 输入或能力 | 选型 | 职责 |
|---|---|---|
| CSV、JSON、Parquet | Polars 1.x 原生读取 | 表格读取、清洗、类型转换、筛选、连接、聚合和惰性计算 |
| XLSX | fastexcel（calamine 引擎） | 只读 Excel；不处理编辑、样式、公式计算或输出 |
| 分析结果 | Pydantic v2 | 返回受类型、字段、数组数量和总大小约束的结构化结果 |

Polars 官方 Excel 读取说明推荐 fastexcel 引擎：[Polars Excel](https://docs.pola.rs/user-guide/io/excel/)。fastexcel 可直接对接 Polars 而不依赖 PyArrow：[fastexcel](https://github.com/ToucanToco/fastexcel)。P3 Docling 面向文档 AST 与 RAG，P4 Polars + fastexcel 面向表格数据分析，同一请求由能力路由选择主路径，不默认双解析。

当前不做 Text2SQL、模型生成 SQL、业务数据库直接查询、Excel/图表生成。DuckDB、SQLGlot、PyArrow 直接依赖、openpyxl、xlsxwriter、Altair 和 vl-convert-python 均不进入基线；具体输出业务出现后重新评估。

## 10. Tool 与 MCP

| 技术 | 裁决 |
|---|---|
| 内部 Tool Schema | Pydantic v2 生成 JSON Schema |
| MCP | 官方 MCP Python SDK 2.x，普通 `mcp` 运行依赖，不安装 `mcp[cli]` |
| Tool Runtime | 自研治理层，统一参数校验、租户权限、幂等、超时、重试、审计、结果大小和脱敏 |
| MCP Client | 当前唯一建设方向；连接受信任且已批准的外部 MCP Server |
| MCP Server | 当前不建设；出现明确跨系统复用需求后单独评审 |

远程连接主选 Streamable HTTP；stdio 只允许静态批准的本地进程；SSE 只作遗留兼容。动态发现不得自动扩大 Tool、Resource 或 Prompt 允许清单。官方 MCP Python SDK v2 提供 Client 和上述传输能力：[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)。MCP 只解决协议互操作，不替代 Tool Runtime 的权限和安全治理，也不承担内部多 Agent 通信。

P0/P2 的普通 HTTP Client 继续使用 `httpx.AsyncClient`。MCP SDK 2.x 内部使用的 `httpx2.AsyncClient` 仅允许存在于 `tools/mcp` Adapter 内，不得扩散为平台通用 HTTP Client；SDK 携带的 Server 侧传递依赖也不构成 MCP Server 建设授权。所有直接和传递依赖统一进入 `uv.lock` 和 `uv audit`。

## 11. 持久化与数据访问

| 能力 | 选型 |
|---|---|
| PostgreSQL Driver | Psycopg 3（async + pool） |
| ORM/SQL | SQLAlchemy 2.x async；高性能向量 SQL 可用 Psycopg 明确编写 |
| Migration | Alembic；任何共享库 DDL 需单独评审和明确授权 |
| Vector Type | pgvector-python |
| Checkpoint | langgraph-checkpoint-postgres |
| Redis Client | redis-py async API |
| COS | cos-python-sdk-v5 |

`pgvector-python` 官方支持 Psycopg 3、SQLAlchemy 和 asyncpg；本项目统一选择 Psycopg 3，避免同时维护多套 PostgreSQL Driver：[pgvector-python](https://github.com/pgvector/pgvector-python)。

纯 Agent 侧只选择 PostgreSQL 作为关系型技术事实库，不把 MySQL 作为 Runtime 基础依赖。数据按两个逻辑 DSN 隔离：Agent Runtime PostgreSQL 保存 Run、Step/Invocation、Usage、长期事件、Dispatch Outbox 与 Checkpoint；Agent Vector PostgreSQL 保存 Document、Chunk、Embedding 与向量索引。Agent 自有表使用 SQLAlchemy 2.x async + Alembic，Checkpoint 使用独立 Psycopg async pool + `AsyncPostgresSaver`；两类迁移不得互相接管。复用基础设施连接不等于与 Java 表混写，物理实例/数据库/schema 映射和全部 DDL 属于后续阶段。

### 11.1 四层记忆存储

| 记忆层 | 技术落点 |
|---|---|
| 工作记忆 | LangGraph State + AsyncPostgresSaver |
| 短期记忆 | Agent Runtime PostgreSQL；Redis 只作热点缓存 |
| 情景记忆 | Agent Runtime PostgreSQL 结构化记录；需要语义召回时进入 pgvector |
| 语义记忆 | Agent Vector PostgreSQL 元数据 + pgvector + PostgreSQL FTS |

四层统一经过 Memory Port 和租户/用户/Agent 权限隔离，不引入 Mem0、Zep、Letta 或独立记忆服务。Run Event 与会话原文不是默认长期记忆，只有经过策略筛选、脱敏和结构化后才能提升。

## 12. P1 日志、运行事实与后置可观测能力

| 能力 | 选型 | 说明 |
|---|---|---|
| P1 Log | structlog + stdlib logging | 本地可读、非本地 JSON；显式传播 run_id、task_id、correlation_id，集中脱敏并输出 stdout |
| P1 Runtime Event | Pydantic RunEvent + PostgreSQL + Redis Streams | PostgreSQL 保存长期事实，Redis 只做短期 SSE 交付与 Last-Event-ID 续读 |
| P1 Usage Contract | PostgreSQL Run/Step/Invocation/Usage | P1 记录真实运行耗时并预留 Token 契约；P2 接模型后记录真实 Token，不伪造数据 |
| P1 Observability Port | 内部接口 + no-op 实现 | 为后续 Trace/Metric 留稳定边界，不引入 SDK、Exporter 或平台 |
| 后置 Trace | OpenTelemetry API/SDK + OTLP（重新评审后引入） | 不属于 P1；未来覆盖 Run、Graph、Node、LLM、Tool、RAG、OCR Span |
| 后置 Metrics | OpenTelemetry Metrics + prometheus-client（重新评审后引入） | 不属于 P1；未来从运行事实派生聚合指标 |
| Audit | PostgreSQL append-only 审计事件 | Tool 授权、审批、模型选择、Prompt 版本、数据来源和产物 |
| Agent/RAG Eval | pytest + Pydantic + JSONL/Parquet + Polars + 项目内确定性指标 | 默认不使用 LLM Judge；Ragas、DeepEval 不进入当前基线 |
| 性能与容量 | 当前不选组件 | 业务功能完成后再单独评审压测和性能基线 |

P1 明确不建设监控平台，不引入 OpenTelemetry、OTLP、Prometheus、Collector、Grafana、LangSmith、Dashboard、告警和完整 Metrics。它只保留结构化日志、关联 ID、运行事件、原始用量事实和可观测接口。后续出现容量、排障和 SLO 需求时再形成独立设计，不得把当前接口预留描述为平台已接入。

## 13. 安全技术组件

| 能力 | 选型 |
|---|---|
| 文件类型识别 | `puremagic 2.x` 文件签名 + `mimetypes` + 扩展名交叉校验 |
| 文件/容器预检 | `zipfile` + `pypdf` + Pillow + 大小、页数、对象数、压缩比和路径限制 |
| 恶意文件扫描 | 仅保留未来 Scanner Adapter；ClamAV 不属于当前必选组件 |
| XML 安全 | defusedxml |
| HTML 清洗 | nh3 |
| URL 安全 | 自研 SSRF Policy + ipaddress + DNS 解析校验 |
| SQL 安全 | 当前禁止 Text2SQL 和模型生成/执行 SQL；Agent 自有查询使用受控 Repository 与参数化语句 |
| Secret | pydantic-settings 读取环境/密钥注入；仓库不落明文 |
| Prompt Injection | 来源隔离、指令/数据分区、Tool 白名单、外部内容不可信标记 |

内容审核按当前裁决不做；但文件安全、SSRF、禁止模型生成/执行 SQL、Prompt Injection 和租户隔离是 Agent Runtime 基础安全，不能因此省略。

## 14. 工程质量组件

| 能力 | 选型 |
|---|---|
| 单元/集成测试 | pytest + pytest-asyncio + pytest-cov |
| HTTP Mock | respx |
| 性质测试 | Hypothesis 6.x 开发依赖；仅用于状态机、Schema、预算、重试、幂等和输入边界等底层不变量 |
| Lint/Format | Ruff |
| 类型检查 | mypy strict 渐进启用 |
| 依赖管理 | uv + uv.lock |
| 依赖漏洞检查 | `uv audit --frozen`；复用现有 uv，不新增 `pip-audit` |
| 架构守卫 | 当前项目内 AST 依赖测试 |

骨架阶段使用标准库 `unittest`，是为了零第三方依赖即可验证；组件落地阶段切到 pytest，同时兼容并执行现有 unittest。

## 15. 付费边界

### 必然或可能产生云费用

| 组件 | 费用判断 |
|---|---|
| AIHub/DeepSeek LLM | 按现有企业接口或模型调用规则计费 |
| DeepSeek 服务端 `web_search` | 当前官方价格页未单列搜索费用；必须核实企业合同，若存在独立搜索附加费用则关闭 |
| DashScope `text-embedding-v4` | 免费额度用尽后按量计费 |
| `qwen3-rerank` / 控制台候选 Rerank | 免费额度用尽后按量计费 |
| `qwen3.5-ocr` | 只保留默认关闭的可选接口；当前不启用。未来仅在有可接受免费额度并获单独批准时使用，禁止自动转付费 |
| Tencent COS | 存储、请求和流量费用 |
| 现有 PostgreSQL/Redis/服务器 | 若为云资源，继续产生基础设施费用，但不是新软件授权费 |

阿里云 OCR 当前不属于活动链路或验收依赖。即使未来存在免费额度，也必须配置硬停止并另行批准；不得因本地解析质量不足而自动切换到按量付费。价格和免费额度会变化，重新评审时只能以当期官方页面和预算为准。

### 无软件调用费，但有自建资源成本

LangGraph OSS、FastAPI、Taskiq、Redis、PostgreSQL/pgvector、SQLAlchemy、Alembic、structlog、Docling、pypdf、pypdfium2、Pillow、PaddleOCR/PaddlePaddle、puremagic、semantic-text-splitter、Polars、fastexcel、pytest、Ruff 等均无软件 API 调用费，但会消耗服务器、CPU/GPU、存储、网络和运维成本；锁定版本的许可证和模型权重许可仍须在实施前复核。

## 16. 明确暂不引入

- ASR、TTS、语音、视频输入输出；
- 内容审核模型/API；
- 任何付费商业热点、舆情、新闻、搜索数据源；
- Elasticsearch/OpenSearch、Kafka、RabbitMQ：现阶段 Redis + PostgreSQL 足够；
- Neo4j/图数据库：没有明确知识图谱查询需求；
- LangSmith 必选依赖；
- OpenTelemetry、OTLP、Prometheus、Grafana、Collector、Dashboard 和告警平台（P1 后置）；
- Celery（官方不支持 Windows）；
- MySQL Driver（纯 Agent 技术事实统一使用 PostgreSQL）；
- AutoGen、CrewAI、Dify、第二套 Graph Runtime；
- 向量数据库迁移：继续使用现有 pgvector；
- 新 Embedding 替换现有索引：必须另建索引版本后再评估。
- Apache Tika、RapidOCR、Office 原生解析栈作为必选项、PyMuPDF、pdf2image/Poppler、ClamAV 必选部署；
- 视觉 LLM、收费 OCR 自动兜底、LangChain/LlamaIndex/Agno 文档切片框架；
- cAST、ChunkHive 等代码专用切片器（当前范围是通用办公文档与图片）。
- SearXNG、Playwright、Trafilatura、BeautifulSoup4/lxml、feedparser 等自建搜索与网页抓取栈；
- DuckDB、SQLGlot、PyArrow 直接依赖，以及 Text2SQL 和业务数据库直接分析；
- openpyxl、xlsxwriter、Altair、vl-convert-python 等 Excel/图表生成或兼容兜底组件；
- 第三方 GitHub Skill 作为运行时数据源或可靠性依赖。
- Ragas、DeepEval 和默认 LLM Judge 评测流水线；
- Locust、k6、JMeter、pytest-benchmark 等性能与压测组件；
- Bandit、Semgrep、独立 Secret Scanner 等额外源代码安全平台；
- MCP Server 与 `mcp[cli]`；当前只建设 MCP Client。

## 17. 引入顺序

```text
P0 工程基线
  Python 3.13/uv/uv_build/FastAPI/Uvicorn/Pydantic/HTTPX/pytest/Ruff/mypy
        ↓
P1 Agent Runtime
  LangGraph/AsyncPostgresSaver/Taskiq/Redis Streams/PostgreSQL Outbox
  SQLAlchemy async/Psycopg 3/Alembic/structlog
        ↓
P2 Provider 与 RAG
  OpenAI Async SDK/HTTPX/DashScope Embedding 与 Rerank
  PostgreSQL pgvector + 原生 FTS/COS/Jinja2 Prompt
        ↓
P3 文档与 OCR
  Docling/pypdfium2/PaddleOCR/PP-StructureV3（按需）
  Document AST/确定性质量门禁/结构优先切片
        ↓
P4 公共研究与数据分析
  DeepSeek Responses API web_search/json_schema（复用 P2）
  Polars 1.x/fastexcel（只读 XLSX）
        ↓
P5 MCP、评测与加固
  MCP Python SDK 2.x Client
  pytest/Pydantic/JSONL/Parquet/Polars 确定性评测
  Hypothesis 性质测试/uv audit 依赖漏洞检查
        ↓
P6+ 可观测性专项（需求出现后单独评审）
  OpenTelemetry/OTLP/Prometheus/Grafana/告警
```

P0～P5 局部技术方向和跨阶段总体一致性评审均已确认，最终跨阶段裁决见[Agent 侧 P0～P5 总体技术架构设计](../superpowers/specs/2026-09-02-Agent侧P0-P5总体技术架构-设计.md)。当前仍不得安装依赖、实现代码、连接基础设施、运行 PoC、执行 DDL 或讨论部署实现。[P1 Agent Runtime 实施计划](../superpowers/plans/2026-09-02-P1-Agent-Runtime实施计划.md)仍是冻结的规划参考；只有项目负责人再次明确授权具体下一阶段后，才可重新评审是否执行。

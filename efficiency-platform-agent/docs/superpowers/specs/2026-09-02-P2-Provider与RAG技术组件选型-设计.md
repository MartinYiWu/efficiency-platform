# P2 Provider 与 RAG 技术组件选型设计

| 属性 | 内容 |
|---|---|
| 标题 | P2 Provider 与 RAG 技术组件选型设计 |
| 状态 | 已批准 |
| 作者/负责人 | Agent 平台架构负责人 |
| 创建日期 | 2026-09-02 |
| 最后更新日期 | 2026-09-02 |
| 评审人/批准人 | 评审人/批准人：项目负责人（用户）；批准日期：2026-09-02；批准范围：本文 P2 技术组件基线；证据：本次任务中明确回复“确认将以上内容作为 P2 Provider 与 RAG 技术组件选型最终基线” |
| 关联 ADR/设计/计划 | [纯 Agent 侧总体架构](../../architecture/纯Agent侧总体架构.md)、[Agent 侧技术组件选型](../../architecture/Agent侧技术组件选型.md)、[P1 Agent Runtime 技术组件选型设计](2026-09-02-P1-Agent-Runtime技术组件选型-设计.md) |
| 替代关系 | 无 |
| 适用范围 | 纯 Agent 侧 P2 模型 Provider、Embedding、Rerank、RAG 检索、对象存储和 Prompt 渲染组件；不适用于业务 Agent、Java 侧、部署拓扑、文档解析/OCR、公共数据采集、MCP、评测与监控平台 |

> 本文只确认 P2 技术组件和接入边界。P0～P5 总体选型和评审现已完成，但它不表示依赖已安装、接口已接通、数据库已变更、PoC 已执行或运行质量已验证，也不构成实施授权；实施继续冻结。

## 1. 目标与范围

P2 为 Harnessed Hybrid Multi-Agent Architecture 提供与业务无关的模型调用和检索底座，使 Direct、Workflow、ReAct、Plan-and-Execute、Supervisor 与 Specialist Subgraph 通过稳定端口使用模型、向量检索、重排、对象存储和 Prompt，而不感知厂商 SDK、响应结构、异常类型或配置键。

P2 范围包含：

- OpenAI-compatible LLM/Embedding 通用客户端；
- 非兼容或特殊厂商 API 的 HTTP Provider Adapter；
- DashScope Embedding 与 Rerank；
- PostgreSQL pgvector、原生全文检索及混合召回；
- 腾讯云 COS 官方 Python SDK；
- Jinja2 Prompt 渲染和 Agent 自有类型化消息契约；
- Provider/RAG 的配置、错误、Usage、退出与后续 PoC 边界。

P2 不包含：具体业务 Agent/Workflow/Prompt、业务数据模型、Java 侧接口、部署设计、数据库 DDL、依赖安装、文档解析/OCR、公开数据采集、数据分析、MCP、评测、安全加固专项或监控平台建设。

## 2. 硬约束

1. LangGraph 继续作为唯一 Graph Runtime；P2 不引入第二套 Agent 生命周期或编排内核。
2. 上层只能依赖 Agent 自有稳定端口；厂商 SDK、配置、响应和异常必须停留在 `providers`/`persistence` 适配层。
3. 复用已有连接和密钥配置，但不得把密钥值复制进代码、文档、Prompt、日志、事件或 Checkpoint。
4. 现有向量空间固定为 `text-embedding-v4 + 1024 维 + cosine`；不同模型或维度不得混写同一索引。
5. P2 关系和向量数据继续使用 Agent Vector PostgreSQL 逻辑数据源；不得与 Java 业务表混写。
6. PostgreSQL 原生 FTS 是关键词检索必选能力；`pg_trgm` 只作为未来可选增强，不是 P2 准入依赖。
7. Prompt 模板必须由项目受控发布；外部文本和用户输入只能作为数据变量，不能作为模板源码执行。
8. 当前只选择组件，不安装、不连通、不运行 PoC、不执行 DDL，也不讨论部署方式。

## 3. 最终组件基线

| 技术域 | 最终选型 | 责任边界 | 当前状态 |
|---|---|---|---|
| 通用模型客户端 | OpenAI Python SDK 的 `AsyncOpenAI` | OpenAI-compatible Chat、流式输出及兼容端点调用 | 已确认，未引入 |
| 特殊厂商接口 | `httpx.AsyncClient` + Provider Adapter | Rerank 等非统一 API；统一认证、超时和响应转换 | 已确认；HTTPX 已属 P0，Adapter 未实现 |
| Embedding | DashScope `text-embedding-v4`，1024 维 | 查询和文档向量生成；维度与模型版本进入索引身份 | 已确认，复用配置，未接入 |
| Rerank | DashScope `qwen3-rerank` | 对融合后的候选集合重排；实际模型 ID 配置化 | 已确认，未接入 |
| 向量数据库 | PostgreSQL + pgvector | 向量、元数据过滤和 HNSW 检索 | 已确认，复用基础设施，未执行 DDL |
| PostgreSQL 访问 | SQLAlchemy 2 async + Psycopg 3 + `pgvector` Python 包 | Repository、参数化 SQL、向量类型注册和连接生命周期 | 已确认，未引入 |
| 向量索引 | HNSW + cosine + 1024 维 | 延续现有向量空间，不在 P2 重建索引 | 已确认，未验证 Agent 侧访问 |
| 关键词检索 | PostgreSQL 原生 Full Text Search | 无额外扩展的关键词候选召回和排序 | 已确认，未实现 |
| 模糊匹配增强 | `pg_trgm` | 仅在目标 PostgreSQL 明确可用且质量收益成立时启用 | 可选；当前目标实例不可用且未安装 |
| 对象存储 | 腾讯云官方 `cos-python-sdk-v5` | 文档/产物对象读写、签名 URL 与元数据；通过 Artifact Provider 隔离 | 已确认，未引入 |
| Prompt 渲染 | Jinja2 `ImmutableSandboxedEnvironment` + `StrictUndefined` | 受控模板渲染、未定义变量失败关闭 | 已确认，未引入 |
| Prompt 消息契约 | Agent 自有类型化消息结构 | 表达 system/user/assistant/tool 等消息，不暴露框架对象 | 已确认，未实现 |
| LangChain 边界 | LangGraph 所需 `langchain-core` 基础能力 | 只接受必要基础依赖；直接使用时必须显式声明依赖和边界 | 已确认，未引入完整 LangChain |

具体补丁版本必须在获准实施后的 Windows + Python 3.13 兼容性 PoC 中确定，并由 `uv.lock` 固化。本文不以未验证的版本号制造兼容性承诺。

## 4. P2 逻辑架构

```text
Harness / Strategy / Supervisor / Specialist Subgraphs
                         │
                  Context Builder
                         │
       ┌─────────────────┼──────────────────┐
       │                 │                  │
 PromptRendererPort  ModelProviderPort  RetrievalPort
       │                 │                  │
       │          ┌──────┴──────┐     ┌────┴──────────────┐
       │          │             │     │                   │
   Jinja2     AsyncOpenAI     HTTPX  PostgreSQL         RerankPort
 Immutable      Adapter       Adapter SQLAlchemy/          │
 Sandbox                              Psycopg/pgvector     │
       │          │             │     │                   │
 Typed Message   LLM/Embedding API    pgvector + FTS   qwen3-rerank
 Contract                                                   │
       └──────────────────── Context/Evidence ───────────────┘
                                  │
                            ArtifactProviderPort
                                  │
                         cos-python-sdk-v5 Adapter
                                  │
                              Tencent COS
```

所有调用继续受 Harness 的身份、权限、预算、超时、取消、审计、关联标识和错误归一化约束。P2 Provider 不得自行创建旁路 Run，也不得让 Graph State 保存厂商 SDK 对象。

## 5. 模型 Provider 设计边界

### 5.1 OpenAI-compatible 主路径

`AsyncOpenAI` 作为 Chat 和兼容 Embedding 端点的主客户端。每个 Provider 由配置创建独立客户端，至少隔离逻辑 Provider 名、基础 URL、模型映射、凭据引用、超时、重试上限和并发限制。上层只接收 Agent 自有请求、响应、流式事件、Usage 和错误契约。

不得把 SDK 响应对象、异常、请求 ID 字段或厂商配置键直接传入 Graph State、API 契约或业务 Agent。结构化输出必须先经过边界 Pydantic Schema 校验，校验失败不能作为合法控制指令继续执行。

### 5.2 HTTPX 特殊接口

`httpx.AsyncClient` 负责 Rerank 等非 OpenAI-compatible API。HTTPX 是 P0 已选基础组件，P2 不再增加 DashScope 专用 SDK。Adapter 必须完成厂商认证、请求/响应转换、超时、有限重试、错误分类、Usage 提取和日志脱敏。

### 5.3 明确不引入

- 不引入 LiteLLM Proxy：当前 Provider 数量和兼容接口不足以抵消新增代理层的配置、故障和观测成本。
- 不把 `langchain-openai` 或 `langchain-community` 作为 Provider 基础依赖。
- 不引入 DashScope Python SDK：特殊接口统一经 HTTPX Adapter，避免并存重复客户端栈。

## 6. Embedding 与向量空间

现有向量空间身份固定为：

```text
provider = DashScope
model = text-embedding-v4
dimension = 1024
distance = cosine
index = HNSW
```

Document、Chunk 和索引元数据必须保存模型、维度、距离度量和索引版本。查询只允许命中同一向量空间。更换 Embedding 模型、输出维度或距离度量时，必须创建新索引版本，通过回放、双写或 A/B 验证完成迁移，禁止直接覆盖或把新旧向量混写。

控制台中其他 Qwen Embedding 型号只保留为后续候选，不进入 P2 当前向量空间，也不因免费额度存在而自动替换 `text-embedding-v4`。

## 7. 检索与重排链路

P2 采用单 PostgreSQL 内的向量与关键词双路召回，不引入 Elasticsearch/OpenSearch：

```text
Query
  → 规范化/可选 Query Rewrite
  → text-embedding-v4 查询向量
  → pgvector HNSW cosine Top-K ─┐
  → PostgreSQL FTS Top-K ───────┤
                                ├→ 内部 RRF/加权融合
                                → qwen3-rerank
                                → Context Budget Packer
                                → Evidence/Citation Assembly
```

RRF、加权融合、预算装配和引用组装是 Agent 内部算法与契约，不再引入第三方 RAG 框架。元数据过滤必须与租户/权限过滤共同进入参数化查询，不能在召回后才补做租户隔离。

### 7.1 PostgreSQL 原生 FTS

FTS 使用 PostgreSQL 内建 `tsvector`、查询构造和相关性排序能力，不依赖扩展。中文检索质量必须在后续脱敏语料 PoC 中单独评估；如果分词效果不足，先调整字段、查询与融合策略，再决定是否提出新的组件选型，不得静默引入扩展或搜索引擎。

### 7.2 `pg_trgm` 可选边界

2026-09-02 对当前目标 PostgreSQL 的只读检查结果为 `pg_trgm` 不在可用扩展列表且未安装，因此它从 P2 必选项降为可选项。未来启用前必须重新只读检查 `pg_available_extensions`，明确服务端支持、索引与 DDL 影响，并按共享数据库规则单独获得授权。P2 的正确性和验收不得依赖 `pg_trgm`。

### 7.3 Rerank

主选模型为 `qwen3-rerank`，通过 HTTPX Adapter 接入。模型 ID 必须配置化。控制台出现的 `qwen3.7-text-rerank` 只作为后续候选；在官方 API 模型标识、真实调用和质量 A/B 未验证前，不得写死到代码或宣称可替换当前主选。

Rerank 故障时是否降级为融合排序结果由后续运行策略设计决定；无论采用何种策略，都必须显式记录降级、模型、耗时和 Usage，不能悄然改变结果语义。

## 8. COS 对象存储

腾讯云 COS 使用官方 `cos-python-sdk-v5`，复用现有 SecretId、SecretKey、Region、Bucket 和 Domain 的配置来源。配置复用表示复用受控引用，不表示把值复制到仓库。

SDK 调用必须封装在 Artifact Provider Adapter 内，上层不能直接依赖 COS Client、异常或对象模型。由于 Agent 主链路为异步，SDK 的同步 I/O 在后续实现时必须隔离到受控线程边界并受超时、取消和并发限制约束；不因此引入 `boto3`、`aioboto3` 或另一套对象存储客户端。

P2 不启用 COS Vector Bucket，也不把 COS 当作权威 Run 状态或数据库。对象 Key 必须使用 Agent 命名空间并携带租户隔离语义，签名 URL、下载和上传都必须通过权限与审计边界。

## 9. Prompt 组件

Prompt 渲染固定采用 Jinja2：

```text
Environment = ImmutableSandboxedEnvironment
Undefined behavior = StrictUndefined
Template source = 项目受控、已版本化模板
External/user/model content = 仅作为变量数据
Output = Agent 自有类型化消息契约
```

`ImmutableSandboxedEnvironment` 防止运行时修改沙箱中的已知可变对象，`StrictUndefined` 使缺失变量立即失败，避免静默生成残缺 Prompt。Jinja2 沙箱不是执行任意不可信模板的安全承诺；模板源码只允许来自受控发布流程，还必须由 Harness 限制输入大小、渲染时间、输出大小和敏感字段。

Prompt 版本元数据至少能关联逻辑名称、版本、内容摘要、变量 Schema、状态和来源。具体表结构、发布、灰度和回滚属于后续实现设计，不在 P2 组件选型中展开。

不采用 `ChatPromptTemplate` 作为基础 Prompt 组件，也不使用 Jinja2 与 ChatPromptTemplate 双重渲染。消息角色和内容分段由 Agent 自有契约表达，Provider Adapter 再转换为具体厂商格式。

## 10. LangChain 使用边界

LangGraph 是底层唯一编排运行时。接受其所需的 `langchain-core` 基础依赖，不等于采用完整 LangChain 应用框架：

- P2 不把 `langchain`、`langchain-openai`、`langchain-community` 列为基础必选依赖；
- P2 Provider、RAG、Prompt 和消息契约不得建立在 LangChain 高层对象之上；
- 如果未来某个标准 ReAct Specialist 确有收益，可单独评估 `langchain.create_agent`，但只能作为 Harness 管控的 LangGraph 子图，不能拥有第二套身份、预算、工具、Checkpoint 或事件生命周期；
- 未来代码若直接导入 `langchain-core`，必须将其作为直接依赖声明和测试，不能只依赖传递依赖偶然存在。

## 11. 可直接迁移的配置与新增内容

| 类别 | 复用内容 | P2 新增内容 |
|---|---|---|
| LLM | 详见[ADR-0001 自适应模型策略路由](../../adr/ADR-0001-自适应模型策略路由.md)：当前默认 `deepseek_direct`，候选模型、逻辑能力路由和凭据引用均配置化 | Agent `ModelProviderPort` 与 OpenAI-compatible Adapter |
| Embedding | DashScope endpoint、`text-embedding-v4`、1024 维和凭据引用 | Agent `EmbeddingPort`、向量空间身份校验 |
| Rerank | 现有阿里云凭据引用 | `qwen3-rerank` HTTPX Adapter、响应和错误归一化 |
| PostgreSQL/pgvector | 现有连接配置和向量能力 | Agent 独立逻辑 DSN/命名空间、Repository 与检索端口 |
| COS | SecretId、SecretKey、Region、Bucket、Domain 的受控配置来源 | Artifact Provider Adapter 与 Agent Key 命名空间 |
| Prompt | 无需迁移 Java Prompt 框架对象 | Jinja2 渲染器和 Agent 自有消息契约 |

任何迁移都只迁移配置语义和受控 Secret 引用，不复制明文值，不复用 Java 对象，不让 Agent 写入 Java 所有的数据表。

## 12. Usage、错误与审计边界

每次模型、Embedding 和 Rerank 调用必须能够归一化记录逻辑 Provider、模型、请求类型、状态、开始/结束时间、耗时、重试/降级标记、厂商请求 ID（若可安全记录）和厂商实际返回的 Token/Usage。不得估算并伪装成厂商精确 Usage；缺失时必须标记计量来源和未知字段。

Provider 错误至少需要区分配置、认证、限流、超时、网络、上游服务、响应格式、Schema 校验和取消。原始异常可用于受控诊断，但 API、Graph State 和日志必须使用 Agent 错误契约并脱敏。

RAG 结果必须保留文档/Chunk 标识、来源、检索通道、原始分数、融合顺序、Rerank 顺序和引用信息。不得把未经权限过滤或来源不明的文本直接装入上下文。

## 13. 费用、许可证与供应链

| 组件类别 | 费用判断 |
|---|---|
| OpenAI Python SDK、HTTPX、SQLAlchemy、Psycopg、pgvector Python、Jinja2 | 开源软件本身无按调用费用；仍有算力、网络、维护和供应链治理成本 |
| PostgreSQL/pgvector | 软件可自建使用；现有云数据库继续产生基础设施费用 |
| LLM、`text-embedding-v4`、`qwen3-rerank` | 按现有企业接口、免费额度和当期云计费规则执行；免费额度不是长期零成本承诺 |
| 腾讯云 COS | 继续产生存储、请求和流量费用 |

P2 不引入任何付费商业热点、新闻、舆情或搜索数据源。所有 Python 直接依赖在实施前必须由 uv 锁定精确解析结果，并完成许可证、来源、漏洞和维护状态复核；本文不代替法务或供应链批准。

## 14. 实施前兼容性 PoC 门禁

P1～P5 总体选型完成并再次获得实施授权后，P2 至少验证：

1. Windows + Python 3.13 下所有选中 SDK 可安装、导入和关闭资源；
2. `AsyncOpenAI` 对现有 LLM 兼容端点的普通、流式、超时和取消行为；
3. `text-embedding-v4` 实际返回 1024 维，且查询与既有向量空间一致；
4. pgvector HNSW cosine、元数据/租户过滤和 PostgreSQL FTS 双路召回；
5. 中文脱敏语料上 FTS、向量和混合召回的质量基线；
6. `qwen3-rerank` 的实际模型 ID、输入限制、错误、Usage 和质量收益；
7. COS 合成对象的上传、读取、签名、删除、超时与权限边界；
8. Jinja2 缺失变量失败、环境不可变、输入/输出限制和外部内容数据化；
9. Provider 响应、错误、Usage、日志和事件中不存在 Secret 或厂商对象泄漏；
10. 资源关闭、连接池、线程隔离和并发限制不阻塞 Agent 异步主链路。

PoC 只允许使用隔离/脱敏数据和经授权资源。涉及共享数据库扩展、索引或表的任何 DDL，必须另行展示脚本、影响、只读预检、验证和回滚，并取得明确授权。

## 15. 风险与补偿

| 风险 | 影响 | 当前补偿边界 |
|---|---|---|
| OpenAI-compatible 端点与 SDK 细节不完全兼容 | 流式、错误或 Usage 解析失败 | 实施前真实端点 PoC；保留 HTTPX Adapter 退出路径 |
| 中文原生 FTS 质量不足 | 关键词召回率低 | 用脱敏语料建立基线；通过向量融合和查询策略补偿；新组件必须重新评审 |
| Embedding 模型/维度漂移 | 向量不可比较 | 向量空间身份校验；新索引版本迁移，禁止混写 |
| Rerank 模型标识或 API 变化 | 调用失败或结果漂移 | 模型 ID 配置化；真实 API 和 A/B 门禁 |
| COS SDK 同步 I/O 阻塞事件循环 | 延迟和吞吐下降 | Provider 内线程隔离、超时、取消和并发上限 |
| 把 Jinja2 沙箱误当作任意模板安全执行器 | 资源耗尽或数据泄漏 | 只允许受控模板；StrictUndefined、大小/时间限制和变量 Schema |
| 高层 LangChain 抽象扩散 | 架构边界和生命周期失控 | 基础依赖边界、依赖守卫和按 Specialist 单独评审 |

## 16. 退出与替换策略

- LLM/Embedding/Rerank 均通过稳定 Provider Port 替换；替换不得改变上层 Graph 契约。
- OpenAI SDK 不兼容某端点时，可在对应 Provider 内替换为 HTTPX，不得让兼容差异扩散到 Agent。
- Embedding 替换必须新建向量空间并完成数据迁移与质量验证，不能原地切换。
- Rerank 可在保留融合排序契约的前提下替换或受控降级，必须保留审计和结果语义。
- PostgreSQL/pgvector 若未来替换，必须先定义 Document/Chunk/Vector/Filter 稳定契约、导出格式、双读验证和回退窗口。
- COS 替换只影响 Artifact Provider，必须先完成对象清单、校验和、权限、URL 有效期及双读迁移。
- Prompt Renderer 替换必须保留模板变量 Schema、版本和类型化消息契约，并用回归集证明渲染等价性。

## 17. 完成声明与冻结状态

当前可以声明：

- P2 Provider 与 RAG 技术组件逐项讨论完成；
- 项目负责人已批准本文所列 P2 局部技术基线；
- P2 组件完整性复核未发现缺失的必选第三方技术组件。

当前不能声明：依赖已安装、配置已迁移、Provider 已连通、向量/FTS/Rerank 已验证、Prompt 已实现、COS 已访问、DDL 已授权或执行、系统可运行或可生产使用。

P0～P5 总体选型和评审已经通过，但在项目负责人再次明确授权具体实施范围前，P1/P2 实施计划、依赖安装、代码、PoC、基础设施连接和 DDL 均保持冻结。

## 18. 官方依据

- [OpenAI Python SDK](https://github.com/openai/openai-python/blob/main/README.md)
- [阿里云向量与重排序模型](https://help.aliyun.com/zh/model-studio/embedding-rerank-model/)
- [阿里云通用文本排序模型 API](https://help.aliyun.com/zh/model-studio/text-rerank-api)
- [pgvector-python](https://github.com/pgvector/pgvector-python)
- [PostgreSQL Full Text Search](https://www.postgresql.org/docs/current/textsearch.html)
- [PostgreSQL pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html)
- [腾讯云 COS Python SDK](https://cloud.tencent.com/document/product/436/31356)
- [Jinja2 Sandbox](https://jinja.palletsprojects.com/en/stable/sandbox/)
- [LangGraph Overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangGraph Python package metadata](https://github.com/langchain-ai/langgraph/blob/main/libs/langgraph/pyproject.toml)

## 19. 版本历史

| 日期 | 作者/负责人 | 变更摘要 |
|---|---|---|
| 2026-09-02 | Agent 平台架构负责人 | 汇总 Provider、Embedding、Rerank、pgvector、PostgreSQL FTS、COS、Prompt 和 LangChain 边界的逐项裁决，并记录项目负责人的 P2 整体批准；批准不包含实施、连接、PoC 或 DDL |

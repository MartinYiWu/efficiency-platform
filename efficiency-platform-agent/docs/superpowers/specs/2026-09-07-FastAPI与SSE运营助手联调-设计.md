# FastAPI 与 SSE 运营助手前后端联调设计

## 1. 文档状态

| 项目 | 内容 |
|---|---|
| 文档类型 | Agent 侧技术设计 |
| 适用范围 | 运营助手文本对话页面与 Python Agent 的本地联调 |
| 当前状态 | 已确认方案，待实施前审查 |
| 目标页面 | `/ai-assistants/operations/chat` |
| 前端地址 | `http://127.0.0.1:5190` |
| Agent 地址 | `http://127.0.0.1:8080` |
| 模型 | 默认真实 DeepSeek；Fake 仅用于自动化测试显式覆盖 |
| 输入输出 | 仅文本输入与文本流式输出，不涉及语音、视频、文件上传和平台发布 |
| 部署范围 | 不定义部署拓扑，不涉及 Java 侧 |

本文只定义前后端联调所需的 Agent 侧协议、运行接线和验收边界。它不代表已经实现、已经启动服务、已经完成真实模型质量验收或具备生产运行能力。

## 2. 背景与当前差距

当前运营页面已经可以完成布局、输入和本地消息展示，但发送动作只更新 React 本地状态，没有调用 Agent API。现有 Agent 侧已经具备 FastAPI 应用工厂、Run 请求/响应契约和有限 SSE 编码能力，但应用工厂需要外部注入运行服务，当前组合根仍是 S2 Fake/InMemory 测试组合根。

因此本次联调设计必须补齐以下边界：

1. FastAPI 应用能够在本地组合真实 DeepSeek Provider；
2. 创建 Run 与执行 Run 解耦，创建请求不能等待模型完整响应；
3. SSE 能够发送运行状态、模型输出增量和终态；
4. 前端能够处理创建、流式接收、失败、取消、刷新查询和断线重连；
5. 真实 API Key 只存在 Agent 进程，不能进入浏览器、事件、日志或前端配置；
6. 本地联调不依赖 Redis、PostgreSQL、COS 或 Java 服务，但接口边界必须为后续真实 Provider 保留替换点。

## 3. 方案裁决

### 3.1 采用方案

采用 **异步 Run + GET SSE 事件流**：

```text
前端 POST /v1/runs
        │
        │ 返回 run_id、queued
        ▼
前端 GET /v1/runs/{run_id}/events
        │
        │ 接收生命周期事件与 assistant_delta
        ▼
FastAPI SSE 桥接
        │
        ▼
Agent Runtime 后台执行
        │
        ├─ Strategy Router
        ├─ Operation Supervisor / Specialist
        ├─ DeepSeek Streaming Provider
        └─ Run/Event/取消/预算治理
```

`POST /v1/runs` 只负责校验身份、建立 Run、写入初始事件并调度后台执行；SSE 负责实时交付。已有 `CreateRunRequestV1`、`RunViewV1`、`RunEventV1` 和租户头校验继续复用，不创建第二套入站请求或运行生命周期。

### 3.2 不采用的方案

1. 同步 POST 完整返回后再伪装 SSE：无法实时输出，不适合长任务和取消。
2. 单个 POST 直接返回 SSE：浏览器不能使用原生 `EventSource`，Run 创建、重连和查询边界不清晰。
3. 前端直接调用 DeepSeek：会暴露密钥，绕过 Agent Harness、预算、租户和模型策略治理。

## 4. 后端 API 设计

### 4.1 创建 Run

```http
POST /v1/runs
Content-Type: application/json
X-Tenant-ID: tenant-demo
```

请求复用 `CreateRunRequestV1`：

```json
{
  "contract_version": "run.create/1",
  "request_id": "ui-唯一请求号",
  "tenant_id": "tenant-demo",
  "user_id": "user-demo",
  "input_text": "请为新品发布生成小红书、微信公众号和今日头条三套独立文案",
  "requested_strategy": null,
  "workflow_id": null,
  "strategy_payload_schema_version": "strategy.none/1",
  "strategy_payload": {}
}
```

响应仍使用 `RunViewV1`，HTTP 状态保持 `201 Created`，但成功创建时的状态为 `queued`：

```json
{
  "contract_version": "run.view/1",
  "run_id": "run-xxx",
  "request_id": "ui-唯一请求号",
  "status": "queued",
  "strategy": null,
  "output": null,
  "error": null,
  "usage": {
    "input_tokens": 0,
    "output_tokens": 0,
    "cost_microunits": 0,
    "estimated": false
  },
  "checkpoint": null,
  "degraded": false,
  "last_event_id": null,
  "budget_deadline": 0
}
```

运行服务新增“创建并调度”路径，现有 `create_and_execute` 保留给内部兼容和离线测试；API 不得继续等待完整 Graph 执行后才返回。

### 4.2 SSE 事件流

```http
GET /v1/runs/{run_id}/events
Accept: text/event-stream
X-Tenant-ID: tenant-demo
Last-Event-ID: 12
```

现有 `RunEventV1` 继续承载生命周期事件。为避免修改基础事件契约，在其之外新增版本化 `RunStreamEventV1`，专门承载对话流：

| 事件 | 用途 |
|---|---|
| `assistant_started` | 开始生成助手内容 |
| `assistant_delta` | 一段新增文本 |
| `assistant_completed` | 完整助手内容和最终 Usage |
| `stream_error` | 流式过程中的稳定错误 |
| `stream_done` | SSE 终止标记，包含最终 Run 状态 |

示例：

```text
id: 18
event: assistant_delta
data: {"contract_version":"run.stream.event/1","run_id":"run-xxx","sequence":18,"delta":"首先，建议将新品发布拆分为三个内容方向："}
```

终态事件：

```text
id: 26
event: stream_done
data: {"contract_version":"run.stream.event/1","run_id":"run-xxx","status":"succeeded"}
```

SSE 必须支持：

- 从 `Last-Event-ID` 之后续读；
- 新连接先回放已产生事件，再等待新事件；
- 发送 keep-alive，避免长时间无输出时连接被误判断开；
- 收到 `stream_done` 后正常关闭；
- Run 不存在、租户不匹配和游标非法返回稳定错误；
- 事件数据不得包含 API Key、连接串、完整内部异常或未脱敏凭据。

### 4.3 查询、取消和恢复

继续使用：

```text
GET  /v1/runs/{run_id}
POST /v1/runs/{run_id}/cancel
POST /v1/runs/{run_id}/resume
```

取消采用协作式语义：API 写入取消请求，运行节点和流式输出边界检查取消信号，完成清理后进入 `cancelled`。取消不能伪装成成功，也不承诺撤销已经发生的外部副作用。

## 5. Agent 运行组合根

新增 Agent 侧本地开发组合根，职责仅限于本地运行接线，不定义部署方案：

1. 读取现有 Agent `.env`，不输出任何 Secret；
2. 使用真实 DeepSeek API Key 构造 OpenAI-compatible 客户端；
3. 构造 DeepSeek Model Provider、流式 Provider 和模型运行时；
4. 注册运营 Agent、中央 Supervisor、Specialist 和场景注册表；
5. 使用本地 InMemory Run Repository、Event Hub 和 Checkpoint，降低联调前置依赖；
6. 创建 FastAPI 应用并挂载 Run、SSE、查询、取消和恢复路由；
7. 仅允许前端开发地址跨域访问。

本地联调的 InMemory 实现是可替换适配器，不改变后续 PostgreSQL 权威事实层、Redis Streams 事件交付层和真实 Checkpoint 的接口方向。Redis 4.0.8 不支持 Streams，因此本轮不能把 Redis 写入作为页面联调前置条件。

## 6. DeepSeek 流式 Provider

基础 `ModelProvider.complete(ProviderRequest) -> ProviderResult` 保持不变，新增独立可选端口：

```text
StreamingModelProvider.stream(ProviderRequest) -> AsyncIterator[ProviderStreamChunk]
```

DeepSeek 适配器负责：

- 使用真实 DeepSeek 配置；
- 将模型增量转换为 `assistant_delta`；
- 在结束时归并完整内容、Usage 和模型标识；
- 传播取消，不把取消转成成功；
- 处理超时、认证失败、限流和服务端错误；
- 使用 Agent 模型策略动态选择逻辑模型；
- 强模型不可用时允许运行时自主降级，并发出 `model_degraded`；
- 不把完整响应正文写入日志或证据文件。

若某 Provider 没有流式能力，允许在同一 SSE 协议中发送一条完整 `assistant_delta` 后结束，但真实 DeepSeek 联调默认必须走流式能力。

## 7. 前端接入设计

### 7.1 分层

运营页面不得直接调用 Axios。新增 Feature 层：

```text
shared/api/
  agentHttpClient.ts
  sseClient.ts

features/operation-chat/
  operationRunApi.ts
  useOperationChatRun.ts
  operationChatState.ts
```

页面只负责展示消息、状态和按钮；Feature 负责创建 Run、消费 SSE、取消、重连和错误归一化。

### 7.2 SSE 客户端

后端要求 `X-Tenant-ID` 和 `Last-Event-ID`，浏览器原生 `EventSource` 无法可靠附加自定义请求头，因此首版使用 `fetch` + `ReadableStream` 解析 `text/event-stream`：

- 支持自定义租户头；
- 支持断线重连游标；
- 支持 `AbortController` 主动取消；
- 不增加第三方 SSE 依赖；
- 解析器只处理约定的 `id`、`event`、`data` 字段。

### 7.3 页面状态机

```text
idle
  └─ submitting
       └─ streaming
            ├─ succeeded
            ├─ failed
            ├─ cancelled
            └─ waiting_input
```

行为要求：

- `submitting` 禁止重复提交；
- `streaming` 显示增量内容和停止按钮；
- `assistant_delta` 追加到当前助手消息；
- `assistant_completed` 固化最终消息和 Usage；
- `stream_error` 显示稳定错误并保留已生成部分；
- `stream_done` 后恢复发送按钮；
- 刷新页面可通过 `run_id` 查询状态；
- 断线最多有限重连，超过上限转为可重试状态，不无限重连。

## 8. 跨域与配置

FastAPI 仅允许以下开发来源：

```text
http://127.0.0.1:5190
http://localhost:5190
```

允许的请求头：

```text
Content-Type
X-Tenant-ID
Last-Event-ID
```

前端只配置 Agent 基础地址，例如 `VITE_API_BASE_URL=http://127.0.0.1:8080`。DeepSeek API Key、模型池密钥和其他凭据只能存在 Agent 侧配置，不能进入前端环境文件、浏览器请求正文或页面状态。

## 9. 错误与安全边界

### 9.1 稳定错误

前端只消费以下字段：

```json
{
  "error": {
    "code": "MODEL_TIMEOUT",
    "category": "provider",
    "retryable": true,
    "safe_message": "模型响应超时，请稍后重试"
  }
}
```

不得把 Python 异常正文、SDK 响应、请求头、URL 中的凭据或数据库连接串直接返回。

### 9.2 幂等与重复连接

- 前端每次提交生成唯一 `request_id`；
- 相同租户和 `request_id` 重复提交返回原 Run；
- 多个 SSE 观察者各自维护游标，不共享消费位置；
- 服务端不因浏览器断开而立即取消 Run；用户明确点击停止时才调用取消接口；
- 所有外部调用仍受 Harness 预算、超时和取消约束。

## 10. 测试与验收

### 10.1 Agent 侧

1. API 合同测试：创建、查询、取消、恢复、租户隔离和稳定错误；
2. SSE 编码测试：事件 ID、事件类型、JSON 数据、keep-alive 和终止；
3. 流式 Provider Stub 测试：首片段、末片段、Usage、超时、429、取消和客户端关闭；
4. 真实 DeepSeek 手工联调：默认真实模型，限制调用次数和输出预算，不持久化完整正文；
5. InMemory Event Hub 测试：历史回放、并发观察者和 `Last-Event-ID` 续读；
6. CORS 测试：5190 来源允许，未登记来源拒绝。

### 10.2 前端侧

1. API 请求体和响应映射测试；
2. SSE 解析器测试：多行 data、事件边界、异常数据和断线；
3. 对话状态机测试：提交、增量、成功、失败、取消和重连；
4. 浏览器测试：真实输入、真实 HTTP 请求、增量助手消息、停止按钮和错误展示；
5. Network 检查：请求中不得出现 DeepSeek API Key。

### 10.3 人工联调通过标准

在 `http://127.0.0.1:5190/ai-assistants/operations/chat`：

- 输入运营任务后，页面向 8080 Agent 发起创建 Run 请求；
- 页面收到 `run_id` 并建立 SSE；
- 能够看到助手内容逐段出现，而不是等待完整结果后一次性出现；
- 最终输出完整且不重复；
- 模型错误、超时、取消和断线均有可理解反馈；
- 刷新后可以恢复查看 Run 状态；
- 浏览器始终看不到模型密钥；
- 默认使用真实 DeepSeek，Fake 只在自动化测试显式开启。

## 11. 实施顺序

1. 固化 `RunStreamEventV1`、异步创建语义和兼容性测试；
2. 实现本地 Agent 组合根、真实 DeepSeek 默认装配和 CORS；
3. 实现 InMemory Event Hub 与后台 Run 调度；
4. 实现 DeepSeek 独立流式 Provider；
5. 实现 FastAPI SSE 回放、keep-alive、游标和终止；
6. 实现前端 Agent API、SSE 解析器和运营对话状态机；
7. 并行补齐 Agent 契约测试、前端组件测试和浏览器联调测试；
8. 启动本地 Agent 与前端，使用真实 DeepSeek 完成一次人工联调；
9. 联调通过后，再评估 PostgreSQL/Redis 真实运行接线，不把该事项混入首轮页面体验验收。

## 12. 明确不在本次范围内

- Java 网关、Java API 或 Java 数据库访问；
- Redis 4.0.8 升级或任何部署变更；
- 付费商业热点数据源；
- 文件上传、OCR、ASR、TTS、视频和图片生成；
- 平台账号授权和主动发布；
- 监控平台、压测平台和生产部署拓扑；
- 修改基础 `ModelProvider` 为强制流式接口；
- 将 DeepSeek API Key 暴露给浏览器。

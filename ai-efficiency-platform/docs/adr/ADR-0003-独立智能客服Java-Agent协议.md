# ADR-0003：独立智能客服 Java-Agent 协议

- 状态：已接受
- 日期：2026-10-20
- 范围：AI 智能客服首个完整闭环
- 关联设计：`docs/superpowers/specs/2026-10-19-AI智能客服首个完整闭环详细设计.md`

## 背景

智能客服需要发布不可变 Agent Bundle、摄取文档、验证索引、执行问答、订阅事件、取消运行和调试 RAG。既有七类 Agent 接口无法表达 Release Bundle、冻结索引和运行回放所需的强类型契约；直接让业务模块访问新的 HTTP Client 又会破坏 `aiep-platform-ai` 唯一出口。

## 决策

智能客服是独立 Agent，固定 `agent_key=customer-service`，不得复用运营助手的业务状态、Prompt、场景或输出契约。Java 通过以下内部接口访问 Agent：

```text
PUT  /internal/v1/customer-service/releases/{releaseId}
POST /internal/v1/customer-service/ingest-jobs
GET  /internal/v1/customer-service/ingest-jobs/{taskId}
POST /internal/v1/customer-service/index-releases/{releaseId}/verify
POST /v1/customer-service/conversations/{conversationId}/messages
GET  /v1/customer-service/runs/{runId}/events
POST /v1/customer-service/runs/{runId}/cancel
POST /internal/v1/customer-service/rag-debug-runs
```

`CustomerServiceAgentClient` 与 `HttpCustomerServiceAgentClient` 只属于 `com.aiep.platformai.agent` 内部传输层。业务模块只能依赖 `com.aiep.platformai.api.AiInvokeFacade` 和 `api.dto`，不能注入内部 Client。

请求和响应使用固定 `contract_version`、强类型 DTO 和严格未知字段校验。每个请求携带 `X-Trace-Id`；日志只记录标识、阶段、状态、序号、耗时和错误类型，不记录问题正文、Prompt、引用原文、连接串或凭据。

## 超时、重试与失败

- 建连超时沿用 5 秒；智能客服普通请求默认读取超时 180 秒，SSE 默认空闲超时 180 秒。
- 只有带稳定幂等标识的网络级失败允许重试一次；4xx、5xx 和契约错误不得自动重试。
- 非 2xx、空响应、未知字段、事件格式错误和流中断均映射为固定 `AgentTransportException`，禁止伪造成功结果。
- Release 只有 Agent 返回相同 checksum 的 ACK 后才能激活；失败不得改变当前 ACTIVE Release。

## 数据边界

Java 持有知识元数据、Agent 配置、会话、消息、引用、反馈和回放投影。Agent 持有文档处理、检索、模型执行和运行事件事实。浏览器只访问 Java，不能直接访问 Agent 或提交可信身份、Prompt 正文、密钥、数据库连接和任意 Schema。

## 结果

新增智能客服内部协议，不替换运营助手协议。`AiInvokeFacade` 继续是唯一业务出口；新增接口和 DTO 必须由契约测试、Agent 真实调用和最终全链路验收共同验证。

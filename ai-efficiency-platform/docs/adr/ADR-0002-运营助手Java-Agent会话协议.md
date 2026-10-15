# ADR-0002：运营助手 Java-Agent 会话协议

- 状态：已接受
- 日期：2026-10-15
- 范围：运营助手 MVP

## 背景

现有前端直接调用 Agent，会绕过 Java 业务会话、身份、消息、任务和制品持久化。运营助手 MVP 需要同一会话先研究热点，再引用研究结果生成公众号或小红书成稿，同时允许 SSE 进度、断线续读和取消。

## 决策

浏览器只访问 Java `/api/operations/**`。Java 使用以下 Agent 内部接口：

```text
POST /v1/conversations/{conversationId}/messages
GET  /v1/runs/{runId}/events
POST /v1/runs/{runId}/cancel
```

Java 固定注入开发身份 `userId=1`、`tenantId=dev`，浏览器请求不能覆盖。提交消息必须携带 `clientRequestId`；Java 和 Agent 均以租户和请求 ID 做幂等。

Java 持有业务真相：会话、用户/助手消息、运行状态投影、文章制品、制品版本和用户可见错误。Agent 持有执行真相：意图、研究计划、来源采集、证据闭包、模型调用、运行事件和取消状态。

SSE 事件必须包含 `runId`、单调递增 `sequence`、`eventType` 和 `payload`。Java 以 `(runId, sequence)` 去重并持久化投影；浏览器用最后事件序号续读。Java 只有在收到 Agent 终态和完整交付后才保存助手最终消息或制品。

## 超时与失败

- 建连超时 5 秒，普通请求读取超时 30 秒，SSE 使用独立长连接预算。
- 只有同一幂等键的网络级失败允许重试一次。
- Agent 4xx/5xx、流中断和载荷不合法都转换为真实失败；禁止创建伪造成功状态或伪造制品。
- 取消为幂等操作；已终态运行返回当前终态。

## 结果

前端不再依赖 Agent 的地址、身份头和原始事件细节。Java 增加 Agent 类型化客户端以及运营助手 Controller/Application/Repository；Agent 保持内部 HTTP 契约并补齐持久化。MVP 不引入登录和自动发布。

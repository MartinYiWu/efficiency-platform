# 运营助手 MVP 真实接口验收

该目录只通过 Java 公开 HTTP 接口验证真实运行结果，不使用 fixture，也不把测试类断言当作端到端完成证据。

## 运行

先启动 Agent、Java 和真实依赖，并将两个后端的标准输出/错误分别重定向到日志文件：

```powershell
pwsh ./scripts/acceptance/operations-mvp/Invoke-OperationsMvpAcceptance.ps1 `
  -JavaLogPath ./.local-acceptance/current/java.log `
  -AgentLogPath ./.local-acceptance/current/agent.log
```

脚本依次创建业务会话、研究热点、生成公众号成稿和小红书成稿，消费真实 SSE，并检查结果语义。原始请求、响应、事件流和日志错误上下文写到 `.local-acceptance/operations-mvp/<timestamp>/`；该目录不提交 Git。

## 判定

- HTTP 非 2xx、SSE 中断、非成功终态或内容语义不满足要求都会非零退出。
- 研究结果检查排名、标题、摘要、引用闭包和独立来源域名。
- 公众号检查标题、章节和正文长度；小红书检查长度、分段和话题标签。
- Java/Agent 日志命中未处理错误时验收失败，必须分析、修复并重放同一请求。
- 脚本通过不代替人工核读；最终验收报告还需记录数据库落库证据和文章内容是否真正可用。

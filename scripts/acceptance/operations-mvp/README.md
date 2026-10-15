# 运营助手 MVP 真实接口验收

该目录只通过 Java 公开 HTTP 接口验证真实运行结果，不使用 fixture，也不把测试类断言当作端到端完成证据。

## 运行

先启动 Agent、Java 和真实依赖，并将两个后端的标准输出/错误分别重定向到日志文件：

```powershell
pwsh ./scripts/acceptance/operations-mvp/Invoke-OperationsMvpAcceptance.ps1 `
  -JavaLogPath ./.local-acceptance/current/java.log `
  -AgentLogPath ./.local-acceptance/current/agent.log `
  -JavaMySqlContainer efficiency-platform-java-mysql `
  -AgentMySqlContainer efficiency-platform-mysql

pwsh ./scripts/acceptance/operations-mvp/Invoke-OperationsResilienceAcceptance.ps1 `
  -JavaLogPath ./.local-acceptance/current/java.log `
  -AgentLogPath ./.local-acceptance/current/agent.log `
  -AgentRestartScript ./.local-acceptance/current/restart-agent.ps1

pwsh ./scripts/acceptance/operations-mvp/Invoke-OperationsBrowserChecklist.ps1
```

主链脚本依次创建业务会话、研究热点、生成公众号成稿和小红书成稿，消费真实 SSE，并检查结果语义。韧性脚本验证幂等、游标重连、Agent 重启恢复、取消和非法引用；`AgentRestartScript` 必须真正停止旧 Agent、确认端口释放、用当前代码重新启动并等到 readiness 成功。原始请求、响应、事件流、数据库查询和本轮日志写到 `.local-acceptance/`；该目录不提交 Git。

正式验收按 `docs/acceptance/2026-10-15-运营助手质量完善验收矩阵.md` 的 OA-01～OA-12 执行。证据目录只保存脱敏请求、响应、SSE、只读数据库查询和本轮新增日志片段，不保存密钥、完整 Prompt、模型推理或数据库连接串。

## 判定

- HTTP 非 2xx、SSE 中断、非成功终态或内容语义不满足要求都会非零退出。
- 研究结果通过 Agent 本轮增量日志检查真实模型调用次数，并检查排名、标题、摘要、HTTPS 引用闭包和至少两个独立来源域名。
- 公众号检查 3000～4000 中文字符、标题、章节、引用边界和 Markdown/复制/下载/HTML 一致性；小红书检查指定条目、分段和 5～10 个话题标签。
- Java/Agent 日志只扫描本轮起始偏移之后的内容；命中未处理错误或用户正文泄漏时验收失败，必须分析、修复并重放同一请求。
- 主链脚本从两个真实 MySQL 容器导出会话、消息、run、artifact、Agent event 和排名快照只读证据；容器不存在、SQL 失败或库名不匹配即失败。
- Agent 重启恢复、SSE 断线续读、幂等、取消和非法引用必须使用真实运行状态验证。
- 浏览器脚本只创建 OA-09 证据目录和检查清单，不会把模拟浏览器结果写成通过；必须在真实浏览器中完成截图、Network 和 Console 检查。
- 脚本通过不代替人工核读；最终验收报告还需记录文章内容是否真正可用。

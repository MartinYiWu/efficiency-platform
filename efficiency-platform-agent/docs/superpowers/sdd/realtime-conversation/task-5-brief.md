# Task 5 任务简报：前端思考动效、打字机和 SSE 终态保护

## 目标

运营助手提交后只显示助手头像和三点思考动效；首个非空 SSE delta 到达后切换为字素级打字机；不展示任何阶段或推理文字。

## 文件所有权

- 可修改：`D:/efficiency-platform/ai-efficiency-platform-ui/src/features/operation-chat/messageReducer.ts`
- 可修改：`D:/efficiency-platform/ai-efficiency-platform-ui/src/features/operation-chat/sseClient.ts`
- 可创建：`D:/efficiency-platform/ai-efficiency-platform-ui/src/features/operation-chat/StreamingAssistantContent.tsx`
- 可修改：`D:/efficiency-platform/ai-efficiency-platform-ui/src/pages/operations-assistant/chat/OperationsChatPage.tsx`
- 可修改：`D:/efficiency-platform/ai-efficiency-platform-ui/src/pages/hr-assistant/chat/HrChatPage.module.css`
- 可修改对应测试；仅安全 Markdown 渲染确有必要时修改 `package.json`。
- 不得修改 Agent 后端文件。

## 必须满足

- 先写失败测试并实际确认按预期失败，再写生产代码。
- `submitting/streaming` 且当前 Run 尚无非空助手正文时显示无文字三点动效。
- 首个非空 delta 到达后立即隐藏思考动效。
- 权威正文和可见正文分离；打字机按 Unicode 字素推进，支持中文与 Emoji。
- `prefers-reduced-motion` 时直接显示当前权威正文。
- 取消、失败、澄清、会话切换和卸载清理动画。
- SSE 客户端遇到 `stream_done` 后立即停止交付同批后续事件。
- reducer 在终态后忽略迟到 delta/phase/assistant_started，状态不得回退。
- `phase_started` 不渲染任何阶段文案。
- 助手 Markdown 必须安全渲染，用户消息保持纯文本；不得启用原始 HTML。
- 所有新增代码注释使用中文。
- 不运行 Git，不启动常驻服务。

## 验证

至少运行：

```powershell
pnpm.cmd test -- src/features/operation-chat/messageReducer.test.ts src/features/operation-chat/sseClient.test.ts src/features/operation-chat/StreamingAssistantContent.test.tsx
pnpm.cmd typecheck
pnpm.cmd lint
```

把 RED 命令/失败原因、GREEN 命令/结果、修改文件、自查结论写入 Agent 项目的 `docs/superpowers/sdd/realtime-conversation/task-5-report.md`。

# Task 5 前端思考动效、打字机和 SSE 终态保护实施报告

| 属性 | 内容 |
|---|---|
| 状态 | 已完成 |
| 负责人 | Codex Task 5 实施代理 |
| 适用范围 | `ai-efficiency-platform-ui` 运营助手实时对话前端 |
| 更新时间 | 2026-09-08 |
| 关联任务 | `task-5-brief.md` |

## 实施结论

- `submitting` / `streaming` 且当前轮尚无非空助手正文时，页面只新增助手头像和三个无文字圆点；首个非空 delta 到达后立即切换为助手正文。
- 权威正文继续保存在 reducer 消息状态；`StreamingAssistantContent` 只维护可见字素计数，按 `Intl.Segmenter` 的 Unicode grapheme 推进。显示模式明确分为 `typing`、`complete` 和 `frozen`：成功终态继续追赶权威正文，取消、失败和澄清冻结已可见部分并清理定时器。
- 冻结状态存于助手消息自身的 `frozen` 标记，而非依赖当前会话总状态；因此新一轮提交不会令已取消、失败或等待澄清的旧消息重新开始打字。`waiting_input` 中同一 Run 迟到的 `assistant_delta`、`assistant_started` 和 `phase_started` 会在 reducer 入口直接忽略，也不会推进事件游标。
- 减少动态效果直接显示当前权威正文；会话切换和组件卸载会清理定时器，新的助手消息以消息 ID 为 React key 创建独立动画实例。
- `stream_done` 交付后 SSE 生成器立即返回；reducer 在终态忽略迟到的 SSE delta、phase 和 assistant 生命周期事件，状态不再回退。
- `phase_started` 未被渲染；助手 Markdown 通过 `react-markdown` 且 `skipHtml` 渲染，不启用原始 HTML。用户消息仍使用 React 纯文本节点。

## RED 证据

先新增失败断言，且在任何生产代码变更前执行以下命令：

```powershell
pnpm.cmd exec vitest run src/features/operation-chat/messageReducer.test.ts --reporter=verbose --testTimeout=5000 --hookTimeout=5000
```

失败原因：`终态后忽略迟到的正文和生命周期事件，避免状态回退` 期望 `succeeded`，实际为 `streaming`；说明迟到的 `assistant_delta` 会回退终态。

```powershell
pnpm.cmd exec vitest run src/features/operation-chat/sseClient.test.ts --reporter=verbose --testTimeout=5000 --hookTimeout=5000
```

失败原因：`同一响应块出现 stream_done 后不再交付后续事件` 期望 sequence 为 `[1, 2]`，实际为 `[1, 2, 3]`；说明同批次终态后仍继续交付事件。

复核追加的失败测试在以下命令中确认：

```powershell
pnpm.cmd exec vitest run src/features/operation-chat/StreamingAssistantContent.test.tsx --reporter=verbose --testTimeout=5000 --hookTimeout=5000
```

失败原因：`stream_done` 先到时组件实际输出完整 `<p>你好</p>`，而非从空可见正文继续追赶；取消后实际输出 `完整正文`，而非冻结 `完`；Markdown 外链缺少 `target="_blank"`。三个断言均在生产代码修改前实际失败。

本轮状态复核新增失败断言也在生产代码修改前执行：

```powershell
pnpm.cmd exec vitest run src/features/operation-chat/messageReducer.test.ts src/pages/operations-assistant/chat/OperationsChatPage.test.tsx --reporter=verbose --testTimeout=5000 --hookTimeout=5000
```

结果：12 项中 3 项失败。澄清后的同 Run delta 将 `已展示部分` 错误追加为 `已展示部分迟到正文`；失败消息没有 `frozen` 标记；冻结消息进入新一轮提交后错误展示为 `完整正文`。同时，“首个非空 delta 到达后立即移除三点思考动效”通过。该次 jsdom 测试同时输出 Ant Design 既有 `height: NaN` 样式警告，不影响断言。

## GREEN 与质量门禁

```powershell
pnpm.cmd exec vitest run src/features/operation-chat/messageReducer.test.ts src/features/operation-chat/sseClient.test.ts src/features/operation-chat/StreamingAssistantContent.test.tsx src/pages/operations-assistant/chat/OperationsChatPage.test.tsx --reporter=verbose --testTimeout=5000 --hookTimeout=5000
```

结果：4 个测试文件、22 个测试全部通过，包含成功终态追赶且无活动 timer、取消冻结、冻结后新一轮、澄清后同 Run 迟到 delta、首个非空 delta 隐藏三点动效和安全外链。

```powershell
pnpm.cmd typecheck
pnpm.cmd lint
```

结果：两项命令均以 exit code 0 完成。

简报指定的 `pnpm.cmd test -- ...` 调用已执行；当前桌面命令包装在 30 秒观察窗口内只输出 Vitest 启动横幅、未返回退出状态，因此最终 GREEN 证据采用同一 Vitest 配置和同一指定文件的直接 `pnpm.cmd exec vitest run` 命令。未启动常驻服务。

## 修改文件

- `ai-efficiency-platform-ui/package.json`
- `ai-efficiency-platform-ui/pnpm-lock.yaml`
- `ai-efficiency-platform-ui/src/features/operation-chat/messageReducer.ts`
- `ai-efficiency-platform-ui/src/features/operation-chat/messageReducer.test.ts`
- `ai-efficiency-platform-ui/src/features/operation-chat/sseClient.ts`
- `ai-efficiency-platform-ui/src/features/operation-chat/sseClient.test.ts`
- `ai-efficiency-platform-ui/src/features/operation-chat/StreamingAssistantContent.tsx`
- `ai-efficiency-platform-ui/src/features/operation-chat/StreamingAssistantContent.test.tsx`
- `ai-efficiency-platform-ui/src/pages/operations-assistant/chat/OperationsChatPage.tsx`
- `ai-efficiency-platform-ui/src/pages/operations-assistant/chat/OperationsChatPage.test.tsx`
- `ai-efficiency-platform-ui/src/pages/hr-assistant/chat/HrChatPage.module.css`
- 本报告。

## react-markdown 工程说明

- 版本固定为 `10.1.0`，本地已安装包元数据声明 MIT 许可证；锁文件同样锁定该版本。
- 已安装发行文件共 9 个、原始体积 52,637 bytes；`package.json` 标记 `sideEffects: false`。这是包自身发行文件体积，实际产物体积仍取决于 Vite 的依赖收集与压缩，未将此数值误作 gzip bundle 大小。
- 当前只有 `StreamingAssistantContent` 直接依赖该包。若后续移除，需改回受控的纯文本或替换 Markdown 渲染器、删除直接依赖及 lockfile 解析项，并保留/迁移原始 HTML 禁用与外链 `target`/`rel` 安全测试；成本局限于该组件与其测试，但会失去现有标题、列表、代码和链接 Markdown 呈现。

## 自查与未验证项

- 未读取 `.env`，未修改 Agent 后端，未执行 Git，也未启动常驻服务。
- `react-markdown` 运行时依赖与锁文件均固定为 `10.1.0`；未安装原始 HTML 解析插件，外链强制使用 `_blank`、`noopener` 和 `noreferrer`。
- 已以组件测试覆盖 Unicode Emoji 字素、减少动态效果、成功终态追赶、取消/失败/澄清冻结、完成后无活动 timer、冻结后新一轮、澄清后迟到事件、首个非空 delta 思考动效隐藏、原始 HTML 不生成 DOM 元素及安全外链；未进行浏览器实机视觉验收或真实 SSE 后端联调，因本任务不授权启动服务。

## 最终独立审查闭环

独立审查发现“新请求已提交、但新 Run 尚未绑定”窗口可能接收旧 Run 迟到事件。新增回归先复现为 1 项失败，再加入窗口保护；最终专项结果为 4 个测试文件、23 项全部通过，前端全量结果为 26 个文件、71 项全部通过。独立复核确认该 Important 已关闭，且正常流在 `run_created` 后才建立 SSE，不会误伤首轮正常响应。

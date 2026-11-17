# 聊天与交付样式对齐证据

## 只读参考

- 旧工程 `D:/work-place/jjcy-ai-platform/ai-platform-web/src/views/ai/chat/index.vue` scoped 样式。
- `src/components/ai/AiMarkdownRenderer.vue`、`AiAnswerEvidencePanel.vue`、`AiAnswerEvidenceDrawer.vue`。
- `src/views/ai/operation-assistant/index.vue` result-section/result-markdown 及 task-detail.vue 成果容器。

## 修正

- 用户气泡采用旧 #1677ff/白字/8px 圆角；助手采用白底、#e7edf5 边框、14px 16px 内距和原 0 8px 22px 阴影。消息头像采用32px灰底圆形，消息行10px gap、14px间距。
- 移除 composer 自创蓝色 focus、外套边框阴影、无边框 textarea、桌面按钮固定高度和输入内距覆盖；输入和主按钮交由原 design-system 决定。保留发送、停止、Enter 及短屏输入限制。
- MarkdownContent 直接迁入旧 AiMarkdownRenderer 样式：14px/1.78行高、18/17/15标题、原代码块、表格和引用样式；安全渲染实现不变。
- 引用内容采用旧 evidence-panel 的16px内距、#e2e8f0边框、8px圆角、蓝色小标题及灰色元数据；原文容器采用旧 operation-result-markdown 的14px内距/#fbfdff底色。
- 交付容器采用旧 task-detail 的22px内距/#e5eaf3边框；结构化子块采用旧 result-section 的12px内距/#e2e8f0边框/#fbfdff底色。
- 未修改 API、业务流程、composables、事件处理或测试断言，无外部业务调用。

## 定向验证

- 指定 CSS/Vue 文件 Prettier 检查通过。
- 指定 Vue 文件 ESLint：0 error；保留已有 attributes-order 和安全处理后的 v-html 警告。
- `pnpm typecheck` 通过（exit 0）。
- 截图、旧新计算样式对照及最终全量由主 agent 统一执行；本记录不宣称这些检查已通过。

## 最终色板清理（2026-11-03）

生效范围为 CustomerServiceChatPage.module.css 全部桌面与移动媒体规则，以及 CustomerServiceChatPage.vue 的 scoped 副标题样式；不触碰全局设计源。

- 历史标题/列表、来源按钮使用旧 --text-primary；次要描述、来源标签、进度文字用 --text-secondary；提示与副标题用 --text-tertiary。
- 分栏边界用 --border-primary；来源区分隔线用 --border-secondary；历史 hover/进度底色用 --bg-secondary。
- 空态图标采用旧 --primary-color/--primary-bg，重命名动作使用 --primary-color，错误/删除文字使用 --color-error。
- 移除 .answer 的父文字颜色覆盖，由直接迁入的 AiMarkdownRenderer 样式确定正文 #111827。
- 修复消息头像组合选择器被旧单独 .assistantAvatar 覆盖的问题，实际生效恢复旧32px/圆形/#e5e7eb底/#374151文字。

保留的局部固定颜色有明确旧源依据：用户气泡 #1677ff/白字，助手气泡 #e7edf5 边框/白底、原阴影；消息头像 #e5e7eb/#374151；会话激活 #eff6ff；chat-title/input 分界 #e5e7eb。旧 Ant List 的 #f0f0f0 行分隔亦保留。引用抽屉内 #2563eb、#64748b、#1e293b、#e2e8f0 来自 AiAnswerEvidencePanel；引用类型 #e0edff/#155eef 来自旧 chat recall-preview-type；原文底色 #fbfdff 来自旧 operation-result-markdown。Markdown 固定色完整来自 AiMarkdownRenderer，未统一蓝紫主题。

本轮仅执行定向 format/lint，不重复正在由主 agent 执行的 coverage 或业务 suite。

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

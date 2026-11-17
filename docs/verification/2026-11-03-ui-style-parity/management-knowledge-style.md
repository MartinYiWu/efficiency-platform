# AI 管理与知识中心样式对齐

本轮只修改展示 CSS 与 SFC 的 `<style>`，未修改 API、业务逻辑、模型、数据、交互或路由；旧工程保持只读，未发出真实 API 或付费请求。

## 旧工程依据

参考根目录：`D:/work-place/jjcy-ai-platform/ai-platform-web`。

- `src/views/ai/prompts/index.vue`、`rag-evaluation/index.vue:743`、`rag-recall-debug/index.vue`、`governance/index.vue` 和 `src/views/knowledge/documents/index.vue` 实际采用 `V1PageShell`。因此这些域标题采用 `src/styles/v1-components.css` 的 22px，而不是独立 `src/components/PageHeader.vue` 的 24px/700。
- `src/styles/v1-components.css:1`：页面间距 16px，页头 gap 12px，说明 margin-top 4px、`--v1-text-muted`；section 标题 16px。
- `src/styles/v1-components.css:35`：V1Section/V1DataTable 16px 内边距、`--v1-border`、`--v1-radius`、`--v1-bg-card`、`--v1-shadow-card`。
- `src/styles/v1-components.css:75`：指标卡 min-height 96px、16px 内边距、13px说明和24px数值。
- `src/views/ai/agents/capability-package.vue:54`：原生 Agent 选择项 padding 12px、6px圆角、透明底、3px左边框，选中/悬浮使用 `#2668e8` 左边框及 `#eff6ff` 背景，辅助字 `#758197`/12px。
- `src/views/knowledge/documents/index.vue` scoped 样式：上传队列 16px 18px；原文预览 padding 14px、V1边框/8px圆角、`#f8fafc` 背景、继承字体和1.7行高。
- `src/components/PageHeader.vue` 已核对，保留为区分来源的参考，并未把其24px标题错误套到V1管理页面。
- `src/styles/design-system.css:188`：Ant卡片实际为16px圆角玻璃卡、head/body水平24px内边距；此规则由公共样式统一加载，本域不覆盖。主按钮紫色渐变及输入、表格、标签、弹窗同样继承公共原样式，不在域内重新指定蓝色主题。

## 修正清单

- `src/pages/ai-center/ai-center.css`：页头标题/说明接入V1 token，去除自创slate说明色；工具栏和筛选间距按V1的12px/8px；Agent选择项复用旧能力包rail规则；指标区按旧V1指标卡修正；原文/回答预览按旧文档预览样式；保留原有列布局、断点、输入宽度及状态行为。
- `src/pages/knowledge-center/KnowledgeCenter.module.css`：去除所有`--ui-*`域级设计token，使用旧V1 token；页头原28px修正22px，section标题20px修正16px；原生目录/结果卡及section接入V1圆角、边框、背景、阴影；移除域内表头色及td行高覆盖，使其继承旧公共Ant表格规则；上传版本区复用旧上传队列内边距。
- 四个知识中心SFC的scoped样式：消除24px/28px标题冲突及自创硬编码文字色；只改style，不改template/script。
- `src/features/ai-center/EvidenceFactsPanel.vue`：证据原文接入旧文档预览样式及V1边框，长内容可换行，现有Ant卡继承公共玻璃样式。

## 选择器与行为复核

- AI页头 `.ai-page h2`、`.ai-page .ui-header p` 覆盖旧域标题与说明；知识页头 `.page .header h2` 同时覆盖原生h2，避免只匹配`h2.ant-typography`漏掉实际页面。
- 仅移除知识域表格视觉覆盖，保留横向滚动、可点击行、分页及禁用/loading绑定；未设置按钮高度或覆盖disabled状态。
- 保留1100px、767px、650px的领域响应式规则与目录移动端横向滚动。

## 定向验证

- `pnpm exec prettier --write`：上述7个修改文件均通过（命令报告unchanged）。
- `pnpm exec eslint src/pages/ai-center src/pages/knowledge-center src/features/ai-center`：退出0，无诊断。
- `pnpm typecheck`：退出0，无诊断。
- 本分工未运行全量coverage/E2E；浏览器旧/新控件对比及最终全量验收由主任务统一执行。

# HR 页面旧样式对照（2026-11-03）

范围：仅 `ai-efficiency-platform-ui/src/pages/hr-assistant/**/*.module.css`（23 个文件）。仅组件规范页 Vue 的静态设计色展示说明获授权同步修正；未修改 hrVnodes、API、业务数据、路由与测试配置。公共设计系统由主任务恢复。

## 旧源依据与本次纠正

- `D:/work-place/jjcy-ai-platform/ai-platform-web/src/components/PageHeader.vue`：标题 24px / 700 / 1.3，标题底部 4px，说明 14px。删除上一轮所有页面共同追加的 22px / 600 标题与 4px 控件圆角；页面标题采用实际 PageHeader 规则。
- `src/styles/design-system.css`：Ant Card 为 16px 玻璃卡、body 24px；Input/Select 12px 圆角、紫色 focus；Tag 8px；主按钮紫色渐变。删除 HR 中后加的白卡/16px padding/4px 控件覆盖，删除面试生成按钮自创蓝紫渐变 important，交还真实旧全局规则。
- 同文件的 table 规则：原生 HTML table（工作台、匹配、预览等）补齐白色 0.7 玻璃背景、灰色 0.8 表头、16px 单元格、低透明分割线与紫色 0.04 hover；Ant Table 继续依赖原有全局。
- `src/styles/v1-components.css` 的 v1-metric-card / v1-metric-icon / v1-metric-content：恢复职位、模板库、匹配、审计和工作台独立统计卡，去掉组合统计条；手工卡 96px 最小高度、16px padding、8px radius、旧 border/shadow，数字 24px。职位图标使用 42px / 10px radius / 20px 与蓝绿紫橙实心语义背景。
- 同文件的 v1-section / v1-filter-bar：撤销页面附加的 border-inline:0 / radius:0，保留响应式 min-width / wrap / overflow；手工筛选与内容面板回到旧 border、8px radius 与 shadow。
- `src/views/ai/hr-assistant/index.vue`：旧 hr-input-panel 为 8px radius、#dbe3f1 border、16px padding；旧 hr-empty 为 #f8fafc、#cbd5e1 虚线、36px icon。上传页恢复面板与上传区域对应规则，强调图标沿用旧紫色；聊天页采用旧 hr-hero 蓝紫浅渐变与旧 scenario-icon 蓝色容器。
- 所有 23 页扫描并将 React slate 中性色映射到旧 text-primary / secondary / tertiary，保留蓝紫混用与成功/警告/错误语义，未将所有状态统一换蓝色。小提示/原生状态标签使用旧 radius-md；原生预览按钮用 radius-sm。

## 检查

- HR 域 ESLint：0 errors，55 个既有 vue/one-component-per-file warnings。
- 23 个 CSS Prettier check：通过。
- 全项目 vue-tsc：通过（组件规范页静态配色修正后再次检查通过）。HR 定向三套测试：3 files / 55 tests 全通过，耗时 254.57s；无 coverage、无真实 API。
- 浏览器旧/新控件视觉对照由主任务统一执行，本文不声明像素级一致。

## 组件规范页静态颜色说明

按旧 design-system.css 精确展示主按钮紫色渐变 #9333EA → #7C3AED、success #10B981、warning #F59E0B、error #EF4444，以及 gray-400 #9CA3AF、border-primary #E5E7EB。单独展示 v1-tokens.css 导航蓝 #2563EB 与页面背景 #F6F8FC；文案明确导航蓝与主要操作紫色承担不同角色，不将导航蓝误称主按钮色。对应色块使用旧 token，紫色色块使用旧按钮相同 135deg 渐变。

## 全局设计系统加载后的 metric 复核

发现工作台 Ant Card metric 仍会被全局 important 强制玻璃/16圆角/24padding。本次将其纯视觉结构替换为旧 V1MetricCard 同构原生 div，直接复用真实 v1-metric-card / is-* / v1-metric-icon / v1-metric-content / title / strong / em。模板库 metric 同样直接复用旧 class，去掉原先 48px 圆形图标；所有值、比较文本、数据源与交互保持原样。职位 metric 标题补齐旧 13px muted / 2px content gap。

在已加载全局的本地 5192 浏览器实测，工作台与注入旧源 CSS 的 reference specimen 对照：card padding16 / radius8 / 白底 / shadow(0 8px 24px rgba15,23,42,.04) / min-height96、icon42×42 / radius10 / 20px、value24 / weight700 / line-height28.8，逐项一致。card实际高度两边均106.781px，容器宽度随页面不同（284px vs specimen360px）故不作为样式判定；数值文字内容宽度也不作判定。证据 hr-metric-computed.json。未重跑HR整套测试。

## 活跃 CSS 颜色最终扫尾

扫描 23 个 module.css，去除 wizard/weights 的 #17243c/#2467ee/#95a0b2/#91a0b5/#b9d3ff/#22b35d/#e5484d/#d14343/#9a6700，模板库 #587194/#53729a/#f3f8ff/#d7e7ff/#e6edf7/#eef3fb、职位 #2463eb/#db7b16/#1d9a62/#7350c9 等迁移旧色。文字分层用 text-primary/secondary/tertiary，线条用 border-primary/secondary，蓝色导航/图标用 v1-primary，紫色强调用 primary/v1-accent，状态及提示底色用 color-success/warning/error/info 与对应 bg。是按控件角色替换，不按最近 RGB 色值匹配。去掉工作台旧自定阴影，复用 v1-shadow-card。

聊天页更正上一轮误用的 HR hero 渐变、紫色 user bubble 与 #175cd3：实际依据旧 src/views/ai/chat/index.vue 的 .message-item.user .message-content 为 #1677ff/white，assistant 为白底、#e7edf5 边框及 0 8px 22px rgba(15,23,42,.05)。头像按该文件 .message-avatar 的 gray-200/gray-700 角色。

最终仍保留的 literal 色值只有白色，以及旧源明确局部例外：#dbe3f1（旧 HR 面板边框，聊天壳/上传面板）、#f8fbff（旧 HR position-summary/信息浅底）、#1677ff/#e7edf5（旧 chat 原样气泡/边框）。玻璃原生表格 rgba 背景、hover 和分隔线严格来自旧 design-system；chat 阴影严格来自旧 chat。没有剩余自创 hex 色板。完整逐文件列表见 hr-color-inventory.json。

本次仅样式，Prettier 全通过；ESLint 0 errors / 55 既有 warnings；按主任务要求未再跑 HR 或 coverage。

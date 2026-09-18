# AI 效能平台前端协作约束

本文件适用于 `D:\efficiency-platform\ai-efficiency-platform-ui` 下的所有前端代码、配置、测试和文档变更。完整规范见 [前端开发规范与约束](docs/前端开发规范与约束.md)；架构决策见 [前端架构设计](docs/superpowers/specs/2026-09-01-前端架构设计.md)。本文件只保留必须执行的规则，不复制完整正文。

## 当前基线

- React 19 + TypeScript 严格模式 + Vite 6 + pnpm 10。
- Ant Design 是唯一基础 UI 与图标体系；样式使用 CSS Modules 和 `src/app/styles/tokens.css`。
- 路由仅在 `src/app/router` 装配；HTTP 实例仅在 `src/shared/api/http.ts` 创建；图表仅经 `src/shared/ui/Chart` 使用。
- 当前目录不是 Git 仓库。不得自行执行 `git init`、提交、推送、重置或删除文件；若未来接入 Git，先检查分支和遗留改动，并以文件白名单提交。

## 变更前必做

1. 阅读相关页面、组件、实体、测试及本文引用的完整规范。
2. 新功能、交互变化或视觉重做先说明目标、范围、验收标准；涉及布局或产品体验时先提供设计并获得确认。
3. 先写能观察目标行为的失败测试，再写最小实现；测试已通过不代表需求被覆盖。
4. 发现基线测试失败、依赖冲突、接口定义不明或超出范围时停止实施，报告证据并请求方向。

## 目录与依赖边界

只允许 `pages → widgets → features → entities → shared` 单向依赖。`app` 只装配 Provider、路由和全局样式，不承载业务逻辑。

- 同层跨模块只通过各模块 `index.ts` 导出访问；禁止用 `../../其他模块` 绕过公开边界。
- `shared` 不得导入任何业务层；`entities` 不得导入 `features`、`widgets` 或 `pages`。
- 页面不得直接调用 Axios、ECharts 或创建 QueryClient；远端数据经实体/功能层 Hook 进入组件。
- 不为单一页面提前创建空目录、通用组件或状态 Store。

## UI 与样式

- 用 Ant Design 提供标准控件；只有存在平台一致性行为时才沉淀 `shared/ui` 组合组件。
- 页面布局必须使用具名 CSS Module 类。禁止无作用域元素选择器（如 `main`、`header`、`aside`）控制业务布局，避免影响 App Shell。
- 颜色、阴影、圆角、间距和 z-index 优先使用 Token；新增全局 Token 必须有跨页面复用理由。
- 每个页面必须在宽屏、中屏、窄屏验证结构变化；不得把桌面布局仅靠缩小字体或挤压宽度适配移动端。
- 交互元素需有可访问名称、键盘焦点和状态语义；图表需有文字摘要或等价信息。

## 数据、接口与安全

- Axios 只能通过 `createHttpClient` 配置；DTO 先用 Zod 校验，再转换为展示模型。
- 服务端状态使用 TanStack Query；Query Key 以实体名开头；Mutation 后只失效相关 Key。
- Zustand 仅用于浏览器本地偏好或布局状态，不能镜像远端接口数据。
- 仅使用 `VITE_` 前缀暴露浏览器环境变量；不得提交 `.env.local`、令牌、个人信息或后端密钥。
- 接口错误、日志和 URL 中不得暴露令牌、权限信息或原始服务端敏感字段。

## 依赖与质量门禁

- 新增依赖前必须说明现有依赖为何不能满足、包体积、许可证、维护状态和移除成本，并获得确认。
- 禁止引入第二 UI 库、第二状态库、Tailwind、Moment、Lodash、jQuery 或未专项决策的富文本/拖拽/聊天组件库。
- 新增或变更 ECharts 图表必须按需加载，并检查生产构建输出；不得把整包图表库放进首屏入口。
- 交付前至少运行：

```powershell
pnpm format
pnpm lint
pnpm typecheck
pnpm test:coverage
pnpm build
pnpm test:e2e
```

- 报告时区分“已实现”“已验证”“未验证”“待确认”；不得把构建成功表述为接口或业务验收通过。

## 文档同步

- 架构、依赖、目录边界、质量门禁或环境变量变化时，同步更新完整规范和 README 的入口说明。
- 新页面或跨模块功能需保留设计、实施计划、测试边界和明确的非目标。
- `.superpowers/` 为本地辅助产物，不能进入业务交付内容。

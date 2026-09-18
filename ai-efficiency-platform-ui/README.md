# AI 效能平台前端

基于 React 的单体 SPA 工程。开发前请先阅读 [协作约束](AGENTS.md) 与 [前端开发规范与约束](docs/前端开发规范与约束.md)；架构设计见 [前端架构设计](docs/superpowers/specs/2026-09-01-前端架构设计.md)，初始化实施过程见 [实施计划](docs/superpowers/plans/2026-09-01-前端项目初始化实施计划.md)。

## 环境要求

- Node.js 20.18+（或 22+）
- pnpm 10+

## 启动

```powershell
pnpm install
Copy-Item .env.example .env.local
pnpm dev
```

`VITE_API_BASE_URL` 是浏览器请求后端的基础地址。前端环境文件不能保存密钥。

## 当前入口与导航

根路径 `/` 统一进入 `/ai-assistants/hr/workbench`。平台只保留 `HrAssistantShell` 一套白色树形导航：工作空间、AI 助手、AI 人事助手的业务页面以及管理项均在同一侧栏中呈现。桌面端默认展示完整名称，可手动横向收合；窄屏改用抽屉导航。

旧的深色 Signal Board 首页、独立 AppShell、仪表盘 ViewModel 与其图表代码已移除，避免同一应用出现两套侧栏和两个首页入口。

## 常用命令

| 命令                 | 用途                         |
| -------------------- | ---------------------------- |
| `pnpm dev`           | 启动本地开发服务             |
| `pnpm lint`          | 执行 ESLint                  |
| `pnpm format`        | 检查代码格式                 |
| `pnpm typecheck`     | 执行 TypeScript 严格类型检查 |
| `pnpm test`          | 执行 Vitest 单元和组件测试   |
| `pnpm test:coverage` | 输出单元测试覆盖率           |
| `pnpm build`         | 构建生产静态资源             |
| `pnpm test:e2e`      | 执行 Chromium 浏览器烟测     |

## 目录规则

业务代码只允许按 `pages → widgets → features → entities → shared` 单向依赖。`shared` 不得引用业务层；页面不得直接调用 Axios；服务端数据只进入 TanStack Query，浏览器本地状态才可进入 Zustand。

## 依赖规则

Ant Design 是唯一基础 UI 库，React Router 是唯一路由库，TanStack Query 是唯一服务端状态方案。新增依赖前必须说明现有依赖无法满足的原因、包体积、许可证、维护状态与移除成本；禁止额外引入 UI 库、状态库、Moment、Lodash、jQuery、Tailwind 或未评审的富文本/拖拽/聊天组件库。

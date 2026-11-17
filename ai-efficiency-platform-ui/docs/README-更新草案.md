# AI 效能平台 Vue 前端（README更新草案）

独立Vue SPA迁移工程。Vue3.5、Router4、Pinia3、Ant Design Vue4、TypeScript、Vite6。原React工程与参考工程只读；本目录可以独立预览，尚不代表已切换正式入口。

协作与实现约束见本目录的AGENTS、完整规范和架构更新草案。依赖实际版本以package.json/pnpm-lock为准。

## 环境与启动

Node20.18（低于21）或22+，pnpm10。

```powershell
Set-Location D:\软件目录\efficiency-platform\ai-efficiency-platform-ui-vue
pnpm install
pnpm dev
```

Vite代理通过`VITE_API_PROXY_TARGET`配置，默认`http://127.0.0.1:8080`。运营API支持`VITE_API_BASE_URL`；不要在浏览器变量写后端密钥。离线验收必须Mock/fixture并阻断未拦截API；直接打开开发页连接真实后端不属于离线验证。

## 当前业务契约

- 客服：`/api/customer-service/*`，消息、引用、反馈、结构化进度与SSE。
- 运营：`/api/operations/*`，URL会话恢复、流、交付物与制品操作。
- 知识：`/api/knowledge/*`，知识库、目录、文档/版本、上传/导入与处理。
- AI管理：`/api/aihub/*`，Agent、Prompt、策略、调试、评测、回放和反馈列表。
- 人事维持现有本地演示能力，本次迁移不表示真实人事服务接通。

不得替换为参考工程旧`/v1`服务或旧认证。

## 命令

| 命令                 | 用途                     |
| -------------------- | ------------------------ |
| `pnpm dev`           | Vite开发服务器           |
| `pnpm format`        | Prettier检查             |
| `pnpm lint`          | ESLint                   |
| `pnpm typecheck`     | 全业务vue-tsc严格检查    |
| `pnpm test`          | Vitest离线单元/组件测试  |
| `pnpm test:coverage` | 覆盖率门禁               |
| `pnpm build`         | 类型检查和生产构建       |
| `pnpm test:e2e`      | Playwright离线浏览器验收 |

定向示例：`pnpm exec vitest run src/pages/ai-center`。先定向检查，最终合并验收再运行全部门禁。通过状态以本次实际命令输出为准，本草案不预先声明全部通过。

## 安全与交付

真实生成、Embedding、rerank需用户明确授权预算，且必须经项目统一付费守卫/固定SQLite总账；禁止裸curl/SDK或另开账本。默认测试只使用Mock，不自动续期预算或真实回归。

业务结构保持`pages → widgets → features → entities → shared`；app仅装配。Markdown统一安全渲染，UI沿用旧版v1风格并在1440/1024/390px验收。没有React兼容层或iframe。

正式承接原入口前，需完成全量功能/路由/离线测试/视觉验收并保留可恢复副本。旧目录删除、覆盖与移动不由本README授权。

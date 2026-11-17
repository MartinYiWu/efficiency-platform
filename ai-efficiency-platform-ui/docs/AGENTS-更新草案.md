# Vue 前端协作约束（待整体验收后纳入根 AGENTS.md）

适用于 `ai-efficiency-platform-ui-vue`。本文件为迁移交付草案，不修改原 React 工程的约束。用户明确指令优先；付费外部调用规范继续有效。

- Vue 3.5、Vue Router 4、Pinia 3、Ant Design Vue 4、TypeScript 严格模式、Vite 6、pnpm 10 为技术基线。业务组件使用 `.vue` 与 `script setup`，纯契约、API、归约器与转换使用 `.ts`。
- 保持 `pages → widgets → features → entities → shared` 依赖方向；`app` 负责装配路由、Pinia、Antd、全局样式，不承载业务动作。
- 禁止 React 兼容层、iframe 或旧入口代替迁移；原 React 工程和参考工程只读。
- 当前客服 `/api/customer-service`、运营 `/api/operations`、知识 `/api/knowledge`、AI管理 `/api/aihub` 契约继续使用；不得导入旧版 `/v1/ai`、旧认证或动态菜单接口。
- 保留各模块既有 fetch/Axios/Zod 边界；不强制重写网络层，不为匹配旧工程增加 Vue Query 或第二状态库。Pinia 用于跨页偏好，页面异步流程用 composables。
- 异步请求必须隔离请求世代和对象标识；卸载与切换对象释放订阅；每次 await 后核验有效性。停止必须与当前提交绑定，不能误取消历史Run；恢复订阅不能再次POST生成。
- Markdown统一通过安全共享渲染器；禁原始HTML和危险协议。业务控件具备可访问名称、键盘操作和禁用状态。
- 默认离线 Mock；测试禁止未拦截API外泄。真实生成、Embedding、rerank没有独立预算授权不得执行，不能直接SDK或HTTP绕过项目付费守卫。
- 改动前读相关原实现及测试；行为变更先写失败用例。不能删除测试或全局stub UI控件绕过门禁。
- 业务样式使用scoped或CSS Modules；全局样式限旧版v1设计令牌和已确认公用类。1440、1024、390宽度分别核验；表格局部横向滚动，不使页面整体溢出。
- 交付运行 `pnpm format`、`pnpm lint`、`pnpm typecheck`、`pnpm test:coverage`、`pnpm build`、`pnpm test:e2e`。报告准确区分已实现、已验证、未验证。
- 不删除、覆盖、移动原工程及用户既有改动；正式切换入口需保留可恢复副本并满足用户授权。不得输出密钥或敏感提示词。

# Vue 前端实施约束

- 本目录承接用户明确授权的 Vue 整体重构；Vue 3、Vue Router、Pinia、Ant Design Vue、TypeScript 为当前技术基线。
- 保留当前前端全部业务功能、接口路径、Zod 校验和付费预算拒绝行为；不导入参考工程的旧后台或认证。
- 目录遵循 app 装配与 pages → widgets → features → entities → shared 的业务依赖边界。
- 原工程和参考工程只读；仅在通过全量验收并保留可恢复副本后切换正式入口。
- 全部页面必须是实际 Vue 组件，不使用 React 兼容层、iframe 或占位页替代迁移。
- 测试先覆盖用户可见行为；默认离线 Mock，E2E 禁止未隔离 API；不得调用真实付费服务。
- 页面与弹层在 1440、1024、390 像素验证；旧版视觉与当前功能分别作为验收基线。
- 交付执行 format、lint、typecheck、test:coverage、build、test:e2e；明确未验证项。
- 不提交、重置、删除、覆盖用户已有改动，不输出凭据。

- UI必须完整复用旧工程实际设计系统：紫渐变主按钮、v1蓝导航、旧控件/玻璃Ant Card与原生V1卡片的不同规则；不要自创ConfigProvider主题或统一改圆角。样式入口与冻结基线规则见完整规范；改主题须运行theme-parity.spec.ts及业务页面视觉验收。

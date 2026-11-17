# 客服业务事务离线验收

2026-11-03：独立 Chromium/Vite 5197 验收 **5/5 通过**（25.1 秒）。未修改产品源码、样式或接口契约，无真实服务、模型、数据库或付费调用。

## 覆盖与证据

- 1440×900、390×900：空历史进入→键盘 Enter 创建会话并提交问题→真实 fetch SSE 解析进度/增量/引用/完成→引用按钮键盘 Enter 打开来源及 Escape 关闭→点赞 PUT→重名 409 保留输入及原名→更正名称 PATCH→刷新恢复原回答与时间线。
- Stateful fixture 校验方法、路径、创建标题、消息契约版本、问题、UUID、改名 trim、反馈正文及状态转换；存储只随合法请求改变。历史刷新只 GET；生成 POST 仍为一次，SSE GET 仍为一次。
- 预算拒绝：消息 POST 返回 402，仅显示公开拒绝，无回答/反馈控件；刷新为空历史消息，不自动再次提交。
- 停止：运行未完成时用户停止，cancel POST 一次，持久状态 CANCELLED；刷新仍显示已停止，不重复生成或取消。
- 缺失引用：完成回答但引用集合为空，不能伪造参考来源。当前引用 Drawer 直接读取消息内引用，不调用 citation API；故未声称覆盖不存在的引用详情 HTTP 失败流程。
- 18 节长回答、长来源标题、处理过程和窄屏引用/重命名弹层可达；页面无横向溢出。低高度布局由既有 customer-service-layout.spec.ts 覆盖，统一门禁由主任务运行。

| 场景 | GET | POST | PATCH | PUT | 响应状态 |
| --- | ---: | ---: | ---: | ---: | --- |
| 1440 完整事务 | 9 | 2 | 2 | 1 | 200、409 |
| 390 完整事务 | 11 | 2 | 2 | 1 | 200、409 |
| 预算拒绝 | 3 | 2 | 0 | 0 | 200、402 |
| 停止 | 7 | 3 | 0 | 0 | 200 |
| 缺失引用 | 9 | 2 | 0 | 0 | 200 |

POST 总数包含创建会话；停止场景另含 cancel。390 完整事务额外 GET 来自通过历史抽屉选择已更名会话。详细请求记录为同目录 `customer-service-*-requests.json`（只含合成测试输入，不含真实提示词或凭据）。每场景未知 API/外源请求均断言为 0；沿用 e2e/fixtures.ts 隔离，未匹配 API 阻断，Vite 后端代理固定 127.0.0.1:1。

截图：`customer-service-{1440,390}.png`、`customer-service-{1440,390}-citation.png`、`customer-service-{1440,390}-rename-error.png`。

## 验证命令

在 `ai-efficiency-platform-ui` 执行：

```powershell
pnpm exec playwright test --config playwright.customer-acceptance.config.ts --workers 1
pnpm exec eslint e2e/customer-service-journey.spec.ts e2e/customer-service-journey-fixture.ts playwright.customer-acceptance.config.ts
pnpm exec prettier --check e2e/customer-service-journey.spec.ts e2e/customer-service-journey-fixture.ts playwright.customer-acceptance.config.ts
```

首次失败属于测试选择器/移动历史可见性假设：停止按钮名称包含图标文字，刷新后移动历史默认收起，嵌套弹层关闭后直接 Escape 不保证聚焦历史抽屉。修正为真实可访问名称、显式展开历史及选择关闭后全部通过，无放宽超时或删减业务断言。

SSE 使用 Playwright fulfill 的真实 `text/event-stream` Response，经产品 fetch reader 与严格 Zod 解析；本测试不模拟网络分块时间与真实后端断线。真实服务联调及付费预算调用未授权，未验收。

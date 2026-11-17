# AI 管理离线事务验收

日期：2026-11-03。对象：当前真实 Vue 页面；所有 API 由浏览器 stateful fixture 模拟，未知 API 由 e2e/fixtures.ts 拒绝。Vite 5196 代理为 127.0.0.1:1，BASE_URL 为空。真实生成、Embedding、rerank、数据库与付费调用均未执行。本报告不代表真实后端联调。

执行：`pnpm exec playwright test --config=playwright.management-acceptance.config.ts --workers=2`，4 条；定向 ESLint、Prettier 检查通过。独立配置仅匹配 management-journey.spec.ts，默认 E2E 自动包含该文件。

| 场景 | 请求与持久状态证据 |
| --- | --- |
| Agent 创建、预算拒绝、审核、刷新 | 第一次 POST 返回 402 且保留 1.0.1，用户显式再次提交成功；创建 JSON 为 semanticVersion=1.0.1、graphKey=customer-service、graphVersion=2、changeSummary=离线验收版本；随后 transition JSON={status:READY}，刷新后仍为 READY。合计 3 POST（其中 1 拒绝）。management-agent-requests.json / management-agent.png |
| Prompt 指定角色编辑 | 只将 USER 正文改为合成测试字符串，PUT 必须完整保留 SYSTEM、ASSISTANT、ordinal、messageKey、trustedInstruction 和 question 变量全部属性；刷新后 GET 原版本返回持久内容，只有 1 PUT。management-prompt-requests.json |
| 数据集及模拟评测 | 创建 DRAFT 数据集；错误 JSON 保留输入且不 POST import；有效 JSON 导入 1 用例，PUT 编辑事实时只保留“保留事实”的等价表述、删除“移除事实”的绑定。刷新读到编辑结果。运行严格冻结 dataset/ customer-service/av/rag/ [{knowledgeBaseId:kb,indexReleaseId:index}]，ACTIVE Release 和 PUBLISHED RAG/Index 由真实下拉选取；GET RUNNING→SUCCEEDED（2 秒真实轮询），刷新后仍见冻结参数，打开结果展示模拟回答/冻结引用 doc-v2。4 次写请求（数据集、导入、编辑、运行）。management-evaluation-requests.json / management-result.png |
| 390×844 | 创建 Modal 的创建和取消均在视口；用例 Drawer 保存和 Close 可达；运行 Drawer 开始/Close 可达。402 预算拒绝保留已选 av/rag，取消并刷新后 POST runs 仍严格只有 1 次，无自动重试。management-budget-requests.json / management-mobile-budget.png |

Fixture 对每个写入的 method/path/JSON 做严格断言后更新存储，后续 GET 由该存储生成；状态操作不以固定空成功响应跳过。未知请求落入隔离守卫，不允许真实服务泄漏。

本轮失败均为新测试的定位/契约标签假设（READY/PUBLISHED 原样显示、Drawer 没有 dialog 角色、隐藏 Drawer 尚保留 DOM），调整测试匹配实际契约后通过；未发现已证实需要改产品的缺陷，未修改产品源码。

限制：现有 Prompt 页面刷新后只有“创建草稿并编辑”，没有已有草稿选择/恢复入口。本用例仅验证保存后重新 GET 同一草稿的数据持久化，不把再次创建新草稿当作刷新恢复；UI 恢复既有草稿编辑未提供。新增用例以 JSON 导入再编辑路径覆盖，未另测逐字段新增入口。真实评测/模型质量、真实服务持久化、真实预算守卫与共享数据库均未验证。截图和请求 JSON 只含合成测试数据。

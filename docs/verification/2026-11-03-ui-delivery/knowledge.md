# 知识中心完整事务验收

2026-11-03，本机真实 Vue 页面、原 Zod 契约、有状态离线 Playwright fixture；没有连接真实后端、数据库、Embedding 或付费服务。

## 结果

- `pnpm exec playwright test --config playwright.knowledge-acceptance.config.ts --workers=1`：2 passed，1440×900、390×900。最终一轮约 30 秒。
- `pnpm exec vitest run src/pages/knowledge-center src/features/knowledge`：5 文件、15 测试通过。
- `pnpm typecheck` 通过；新增文件及三个变动 Vue 的定向 ESLint、Prettier 通过。
- 独立端口 5195，代理目标 `127.0.0.1:1`；复用 `e2e/fixtures.ts` 自动请求隔离。fixture 拒绝所有未知知识请求，默认隔离拒绝其他未 Mock API。

## 完整链路与请求摘要

两个宽度分别从空库开始：必填校验不发送 POST → 创建产品文档库 → GET 详情为 DRAFT、上传禁用 → PUT 启用并 GET 重读 → 新建目录第一次返回 409，保留输入且不自动重试 → 用户确认第二次创建成功并 GET 重读 → 原生 filechooser 选择真实 Markdown 文件 → 上传 → GET 批次先 RUNNING、轮询后 SUCCEEDED → GET 文档为 READY → 打开真实处理任务 Drawer → 发布 → 刷新 GET 文档仍 PUBLISHED、冻结证据模式不变 → 返回库确认当前索引 → 回滚 → 刷新确认回滚索引。

每次事务写请求固定 7 次：POST 创建库 1、PUT 启用 1、POST 创建目录 2（含一次预期409）、POST 单文件上传 1、POST 发布 1、POST 回滚 1。spec 检查 POST 总数6，无自动重复提交。读取按界面实际导航/轮询发生，不使用空成功响应。

fixture 精确断言 JSON 字段及状态前置条件。上传用 Node 原生 FormData 解码 multipart，精确断言只有 `file`、`directoryId`、`evidenceMode`，文件名和 Markdown 字节文本、目录 `dir-1`、证据模式 `EXTRACTIVE_NARRATIVE` 均一致。发布只允许 READY，随后写入发布文档和索引；回滚后更新持久内存状态，由后续 GET 重读验证。Mock 处理只模拟生命周期，不代表实际解析、向量化或线上发布成功。

## 发现与最小修复

390 宽首轮失败：固定 480/520 像素 Drawer 超出视口左侧，处理任务 `Close` 按钮经稳定后位于视口外，Playwright 实际点击超时（30.1秒），上传截图也可见左侧标题与内容被截断。已保留关闭动作及 viewport 回归检查，按失败→修复→通过执行。

仅调整以下 Drawer 的宽度为 `min(原宽度px, 100vw)`：新建知识库、上传文档、处理任务。桌面宽度保持原值；未改 CSS 主题、API、schema 或其他领域。批量导入 Modal 在390宽实测进度和关闭操作可达，不需修改。

## 截图

- [1440上传](knowledge-upload-1440.png)
- [390上传](knowledge-upload-390.png)
- [1440发布刷新](knowledge-published-1440.png)
- [390发布刷新](knowledge-published-390.png)

截图保留长 Markdown 文件名、目标目录、选择的证据模式及发布后的冻结模式。实际后端、真实索引引擎与付费调用未验证。

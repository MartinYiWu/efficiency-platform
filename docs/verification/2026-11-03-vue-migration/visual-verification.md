# Vue 全路由离线视觉验收

## 可重放入口

```powershell
cd ai-efficiency-platform-ui
pnpm exec playwright test --config playwright.visual.config.ts
```

独立配置监听5191，避免与默认5190门禁冲突。测试继承现有e2e/fixtures.ts请求隔离，并通过migration-fixture.ts给知识/AI/客服/运营提供明确的非空合法数据。HR保留页面既有演示数据。任何未配置API、fetch/XHR或非当前源请求都会阻断并使测试失败；无真实生成、Embedding、rerank请求。

## 覆盖范围

- 从真实Vue routes导入全部44个非404业务路由，动态ID替换为fixture ID。
- 1440、1024、390宽度逐页导航，共132次页面检查。
- 检查主体挂载、首个标题可见、浏览器pageerror、文档横溢出、主体横溢出（避免外壳裁切掩盖布局问题）。
- 知识关键上传/新建按钮与HR新建岗位可见；三类聊天输入框位于视口。
- 非空数据展示与加载/契约错误检查。
- 9个代表路由各3宽截图，共27张；截图覆盖知识列表/详情/文档、AI Agent/评测、HR工作台/岗位、运营聊天与客服聊天。

## 发现与修复

- 客服历史消息自动读取timeline，初版fixture漏配；补充合法timeline，未放宽未知请求门禁。
- 客服存在嵌套main，测试改定位main.platform-content，未修改业务结构。
- 含图标的按钮可访问名称包含图标前缀，测试匹配可见名称后缀。
- 路由文件格式化改变引号/换行，测试改直接导入真实routes，不再用文本正则。
- 代表截图目视没有发现知识/运营展示布局问题，未做额外业务改动。

最终增强检查全部通过：3 passed（约2.5分钟），共44页面×3宽度=132次页面检查，零pageerror、零文档/主体横溢出、零未知API/外源请求。1440耗时50.8秒、1024耗时45.8秒、390耗时47.2秒。原始结果见visual-results.json；测试文件及配置eslint、Prettier通过，vue-tsc无本次新增文件诊断。

## 截图索引

| 页面 | 1440 | 1024 | 390 |
| --- | --- | --- | --- |
| 知识列表 | [图](screenshots/knowledge-list-1440.png) | [图](screenshots/knowledge-list-1024.png) | [图](screenshots/knowledge-list-390.png) |
| 知识详情 | [图](screenshots/knowledge-detail-1440.png) | [图](screenshots/knowledge-detail-1024.png) | [图](screenshots/knowledge-detail-390.png) |
| 文档版本 | [图](screenshots/knowledge-document-1440.png) | [图](screenshots/knowledge-document-1024.png) | [图](screenshots/knowledge-document-390.png) |
| Agent | [图](screenshots/ai-agents-1440.png) | [图](screenshots/ai-agents-1024.png) | [图](screenshots/ai-agents-390.png) |
| RAG评测 | [图](screenshots/ai-evaluations-1440.png) | [图](screenshots/ai-evaluations-1024.png) | [图](screenshots/ai-evaluations-390.png) |
| HR工作台 | [图](screenshots/hr-workbench-1440.png) | [图](screenshots/hr-workbench-1024.png) | [图](screenshots/hr-workbench-390.png) |
| 岗位新建 | [图](screenshots/hr-position-1440.png) | [图](screenshots/hr-position-1024.png) | [图](screenshots/hr-position-390.png) |
| 运营聊天 | [图](screenshots/operations-chat-1440.png) | [图](screenshots/operations-chat-1024.png) | [图](screenshots/operations-chat-390.png) |
| 客服聊天 | [图](screenshots/customer-service-1440.png) | [图](screenshots/customer-service-1024.png) | [图](screenshots/customer-service-390.png) |

这是本次迁移的离线挂载/响应式验收，不能替代所有弹层交互或与参考工程的逐像素比对。页面内部滚动区域的截图仅显示当时视口内容。

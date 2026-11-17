# 知识中心功能对照

原工程只读，目标为 Vue 3 script setup + Ant Design Vue。四页全部实现，未发现业务功能遗漏。

| 原页面/组件 | 保留行为与字段 | 验证 |
| --- | --- | --- |
| KnowledgeBaseListPage | 名称/编码/描述/类型/范围/更新时间/状态；分类、trim 搜索、每页10条、点击行与查看导航；新建名称必填、编码正则、类型必填、描述 | KnowledgeCenter + KnowledgeParity |
| KnowledgeBaseDetailPage | 信息、目录、文档、索引；目录 parentId/sortNo；目录筛选与分页；上传、批量；DRAFT/DISABLED激活；PUT保持name/description/knowledgeType；刷新成功后才解锁；历史索引回滚，当前索引无回滚按钮 | KnowledgeCenter + KnowledgeParity |
| KnowledgeDocumentPage | 来源/状态/已发布版本；单文件更新、固定变更说明；冻结证据模式；版本时间/说明/任务；READY发布；任务表；fileId/contentType/effectiveDate | KnowledgeDocument |
| KnowledgeImportPage | 缺ID、加载、禁用提示、回到激活页、目录与文件说明、批量弹层；关闭后销毁弹层，再开为空批次 | KnowledgeParity，弹层由v-if明确重建 |
| KnowledgeUploadDrawer | 仅1文件、目录、PDF/Word/TXT/MD、证据模式、提交中禁用、成功事件与关闭、失败提示 | KnowledgeWorkflows |
| KnowledgeBatchImportModal | 至少2文件、目录、上传、initialBatchId、3秒轮询、终态停止、成功失败计数、进度、失败原因与项目重试 | KnowledgeWorkflows；轮询清理与终态代码核对 |
| ProcessingTaskDrawer | 初始读取、3秒轮询、终态停止、阶段/状态/次数/错误、失败重试、关闭与卸载取消污染 | KnowledgeWorkflows |
| EvidenceModeSelect | 产品/技术允许节选；制度/流程强制全文；说明文本；上传API再次强制校正 | KnowledgeCenter + KnowledgeWorkflows |

API、model、schema、presentation与原工程相同，SUCCESS envelope、Zod strict、全部URL和FormData字段不变。未导入参考工程后台契约。页面新增显式错误重试入口，不改业务结果。

定向测试：初始缺组件RED后实现；现有5文件15例通过。领域eslint通过，Prettier已格式化；vue-tsc输出中知识领域无错误。视觉1440/1024/390已通过全路由浏览器验收，代表截图在screenshots目录。新增覆盖：早发分页晚返回、激活刷新失败仍禁用、批次3秒轮询与终态停止、处理任务关闭后停止轮询。

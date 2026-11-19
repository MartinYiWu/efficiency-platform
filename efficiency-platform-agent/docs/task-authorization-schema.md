# D24 本机授权链部署门禁

当前能力默认关闭，M2尚未完成最终验收；本文不是生产迁移或真实费用授权记录。

## Schema审阅与备份

新增schema仅包含 `task_budget_chains`、`task_authorizations`、
`task_paid_operations`、`task_authorization_schema`，不删除/重置既有财务记录。
DDL集中在 `SqlitePaidBudgetLedger.initialize_task_authorization_schema`，
普通账本构造器不调用它。`operation_limit`冻结根执行更严格的尝试上限。

部署前停止本机所有付费Worker，核实固定用户账本位于本机磁盘且无在途请求；
跨主机或网络共享SQLite不支持。先人工审阅上述DDL及备份目标，
经单独授权后才在Agent工程目录运行以下本机命令。

1. `python -m scripts.migrate_task_authorization --backup-path <新的本机备份文件>`：只读预检。
2. 加 `--confirm`：SQLite一致性备份、备份quick_check、建表、schema version核验、
   迁移前后budget数量/累计调用/累计费用/在途数一致性核验。
3. 核验后仍保持 `EFFICIENCY_TASK_AUTHORIZATION_ENABLED` 未设置。
   只有M2及D24启用门禁通过后才可由本机部署配置显式设为 `true`。

关闭该配置后，已属于task链的授权也不能降级为旧通道继续调用。
备份只用于灾难恢复审计；不得通过恢复旧备份减少已发生费用或复活停止授权。

## 授权与执行

根授权仍来自原本机费用授权流程。启用后首个可信ContextDispatch请求将一个
尚未发生调用的根budget绑定至同一conversation/task/run，冻结最多100元/60次
及原授权更严格限制。无法证明operation归属的历史budget拒绝自动接入，
包括现有停止预算；不得凭改task_id或迁移脚本重新授权这些历史记录。

后继命令为 `python -m scripts.authorize_task_continuation`，必须显式提供
task、父authorization、总金额/HTTP/input/output/reasoning上限、带时区截止
和已人工核实的price-limit JSON数组。无 `--confirm` 只读预览；有confirm才
创建同链新有限授权。后继窗口最长10分钟，累计上限只能收紧，命令幂等。

新execution使用既有fresh execute/ContextDispatch，由当前源/删除/权限门禁
重新准备合法输入；PaidHttp按可信task/run选择本机授权。父授权及旧run保持
停止/过期；`continuation_of`保留父授权与原run恢复关联。已完成合法回执可由
业务层重新规划引用；不会导入或恢复旧LangGraph thread正文。

原 `resume`/TTL刷新协议中的 `CONTINUATION_AUTH_UNSUPPORTED` 拒绝继续保留：
它们操作原execution/旧checkpoint，不能借后继授权复活。HTTP不提供任何创建
费用授权入口。所有实际发送和unknown预留均由同SQLite PaidHttp守卫累计，
operation尝试跨run保留，402及累计429不能用新authorization绕过。

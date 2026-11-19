# Agent记忆部署、恢复与预算操作说明

状态：候选操作手册，未授权生产执行；负责人Codex；更新时间2026-11-19（北京时间）。

## 部署顺序

先核对同版源码、依赖与Schema哈希，再分别执行Java sql目录V16/V17/V18/V19/V20/V21/V22/V23的precheck/up/verify及Agent自有MySQL/PG对应bootstrap。所有DDL由受权管理会话操作；应用启动只核验Schema，不自动建表。共享库trigger1419未解除时不调全局参数、不提权。各rollback只允许规定的未使用空结构；已用授权、UNKNOWN、墓碑、删除水位不可回滚清零。

Java的packet、refresh、summary-persistence、derive、proposals、index、recall、sharing、episodes、promotions和Agent的memory相关新开关逐域灰度，默认关闭；策略、Prompt、Schema和实际Provider容量必须匹配已发布版本。SUMMARY紧凑输出使用derive-prompt/2、derive-schema/2；PROPOSALS/BOTH紧凑输出使用derive-prompt/3、derive-schema/3，不混用schema。HR TASK_ONLY不启候选人长期印象；行政尚未实现。

## 本机费用授权

统一固定用户SQLite位于configuration.paid_budget.default_paid_budget_path()解析的本机路径；不复制为新真实账本、不使用网络共享盘。普通服务构造不迁移task授权Schema；显式迁移先备份/quick_check/verify，操作说明见Agent docs/task-authorization-schema.md。本机authorize_task_continuation.py无--confirm只读预览，确实授权须核实价格、模型、输入/输出/推理token、总调用/金额与绝对截止。业务HTTP不能授权或扩大预算。

同task总上限100元/60次或原更严格值，只可收紧；新execution不复活旧EXPIRED/STOPPED，原operation最多3次累计，UNKNOWN和预留保持占用。402与累计429持久熔断；重启、换进程、换策略、换工作树不续期、不清零。预算审批不等于业务权限审批。

## 恢复与回滚

先应用tombstone、抑制与财务账本，再开放正文与Checkpoint恢复。旧执行的TTL刷新只允许原冻结语义的窄外壳变化，后继付费必须本机有限授权的新execution，不能旧run paid resume。来源失效拒绝旧摘要/案例/索引，缺权限服务时禁用相关内容。

确认候选是CPU动作，不建立索引；索引需单独明确请求。关闭新生成/召回不取消已经配置的CPU删除补偿；DELETED/INDEX ACK必须真实精确回执，UNKNOWN不假成功。任一出错先关闭新能力保留墓碑/抑制/总账，不恢复旧正文或删除审计来清故障。

真实语义验收只能在用户明确有限预算与已核价格后运行；本轮无此授权，不自动执行。

索引发布策略必须明确artifacts.index_mode=PROVISIONED且index_backends仅[agent-pg-memory-index/1]，semantic.enabled必须真实布尔true；未配置索引的策略保持NOT_PROVISIONED与空backend。该清理证明不能随当前开关切换伪造。queryEmbedding需额外发布semantic.queryEmbeddingEnabled=true、原有限授权/已核价目/原task剩余额度；业务HTTP只提供query不能提供授权。

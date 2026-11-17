-- 不可逆删除逻辑阶段/HTTP操作关联。停止全部调度并备份，核实未决CLAIMED/RETURNED/UNKNOWN，另获明确授权后方可执行。
-- 删除后不得自动重建同stage并重发旧业务操作；必须先核对原D06/费用回执。
DROP TABLE agent_context_stage;

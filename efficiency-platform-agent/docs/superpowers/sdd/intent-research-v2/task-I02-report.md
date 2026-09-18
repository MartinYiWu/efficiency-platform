# I02 实施报告：多轮 Reducer、任务隔离与 revision

## 状态

**离线通过。**

本任务只实现 Agent 侧纯确定性状态归约；未调用网络、真实模型、研究工具或数据库，未修改 Java/UI/部署/共享 DDL，未执行 Git 操作。真实持久化 CAS 仍归 X01。

## 交付文件

- `src/efficiency_platform_agent/orchestration/intent_v2/reducer.py`
- `src/efficiency_platform_agent/orchestration/intent_v2/__init__.py`
- `src/efficiency_platform_agent/orchestration/intent_v2/patch_validation.py`
- `src/efficiency_platform_agent/contracts/intent_v2.py`
- `src/efficiency_platform_agent/contracts/research_ports_v2.py`
- `tests/orchestration/intent_v2/test_reducer.py`
- `docs/superpowers/sdd/intent-research-v2/task-I02-brief.md`
- 本报告与独立审查记录

## 已实现边界

- `new_task` 从 revision 0 创建新任务，不继承旧业务字段；任何 `origin=inherited` 操作均以 `INTENT_CROSS_TASK_INHERITANCE` 拒绝。
- 非新任务要求 task 精确一致、base revision 精确一致；相同 task/message 重放幂等返回旧快照，基于同一旧 revision 的后到写入返回 `INTENT_REVISION_CONFLICT`。
- I01 校验结果绑定可信 task、当前消息及可见用户消息集合，不能换绑另一条消息或任务后重放。
- follow-up/resume 必须且只能解析到一个可信引用任务，否则返回 `INTENT_REFERENCE_AMBIGUOUS`。
- explicit、inherited、derived、default 按来源优先级归约；未提及与 clear 区分，append/remove 稳定去重且不存在项为 no-op。
- `TrustedMessageV2.received_at` 是唯一时间锚点：显式或非继承时间修改使用本轮可信 anchor/timezone，纯继承时间保留原 anchor/timezone。
- `unresolved_references` 保留到 Frame，供后续 DecisionPolicy 澄清；Goal 按 id 稳定 upsert，并由 Frame DAG 校验约束。
- scope hash 是可序列化、可回读、防篡改的确定性字段；由目标、业务范围、UTC 规范化时间锚点及 timezone 生成，不含 task/revision/message/provenance。
- Frame 业务字段保留 `FieldValue[T]` 来源；来源约束和输出要求提供受限的叶级 provenance，支持叶级默认补全且不覆盖显式叶值。
- Reducer 是纯函数：不调用模型、工具、系统时间、仓储或数据库。

## 红灯证据

首次只加入行为测试后执行，失败于实现尚不存在：

```text
ModuleNotFoundError: No module named 'efficiency_platform_agent.orchestration.intent_v2.reducer'
```

首轮实现后有 2 项失败：一项因 `new_task` 检查顺序错误而返回 `INTENT_TASK_MISMATCH`；另一项测试错误地把绑定消息 m2 的已验证 Patch 用作 m3 并发写入，Reducer 正确返回 `INTENT_PATCH_CONTEXT_MISMATCH`。前者修复实现顺序，后者修正测试前提后通过。

## 绿灯与回归证据

```text
I02/I01/契约定向：108 passed

意图 V2 + contracts + architecture：
188 passed, 124 subtests passed

Ruff：All checks passed

mypy：Success: no issues found in 4 source files

全量回归：
1127 passed, 275 subtests passed, 2 existing dependency warnings in 35.26s
```

两条全量警告来自既有 Starlette `BlockingPortal` 弃用提示和 Polars `read_excel` 未来返回类型变化，不由 I02 引入。

## 未宣称事项

- 离线通过不代表真实模型产生的 Patch 语义正确，也不代表模型/工具/网络链路已验收。
- I02 固定的是纯函数冲突语义，不包含数据库事务、锁、真实 compare-and-swap、恢复或跨进程一致性；这些属于 X01。
- 旧快照若没有完整叶级 provenance，Reducer 采用保守推导，确保低优先级不能覆盖高优先级；透明默认补全的完整历史能力只对新格式快照成立。

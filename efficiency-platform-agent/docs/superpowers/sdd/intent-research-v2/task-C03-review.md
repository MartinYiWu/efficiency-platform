# C03 规格与质量审查

## 审查范围

依据 `task-C03-brief.md`、总计划 C03、当前 Budget Lease core/contracts、ResearchBudgetAdapter、ToolRuntime、ModelRuntime 及对应测试进行文件级审查。项目规范禁止 Git 操作，因此以白名单文件、源码、定向反例和测试输出作为证据。

## 审查过程

独立审查共三轮：

1. 首轮发现实例预算并发串账、共享来源 scope 泄露、dispatch/release 语义、取消迟到、契约漂移和父账本未接 Runtime 等问题。
2. 第二轮通过自建反例发现租约流式提前交付、构造器状态未累计、reserve/dispatch 竞争、旧 remaining 早退遗留、CAS 误拒绝和 started 诊断提前。
3. 第三轮发现 settlement overrun 丢失实际用量，以及 Model complete 错误映射后 usage 归零。

实施者逐项复现并修复；审查者在稳定快照上重新执行仓库测试及独立 stdin 反例，没有以已有绿灯替代反例验证。

## 最终规格审查

| 检查项 | 结果 |
|---|---|
| tenant/run 隔离与 source/account 共享桶 | 通过 |
| CAS 并发、幂等和冲突关闭 | 通过 |
| reserve/dispatch/settle/release 生命周期 | 通过 |
| 取消、deadline、late 与 delivery gate | 通过 |
| unknown 与 overrun 实际用量保留 | 通过 |
| Tool/Model complete/stream/stream_complete 父账本接线 | 通过 |
| 无双重计账与旧构造器兼容 | 通过 |
| 契约长度、limits、输出预留 | 通过 |
| 不接真实 I/O、数据库或模型费用 | 通过 |

## 最终质量审查

- C03/架构组合：93 passed，78 subtests passed。
- Ruff：All checks passed。
- mypy：C03 source modules 无问题。
- 最终独立反例：账本、审计、返回 usage 均保留真实超额值；正文未提前交付；无 reservation 遗留。

## 结论

**C03 离线规格与质量通过。** 独立审查最终结论 PASS，未发现 Critical、Important 或 Minor。通过仅证明离线契约与单进程 Fake 行为；多 Worker 持久化原子性归 X01。

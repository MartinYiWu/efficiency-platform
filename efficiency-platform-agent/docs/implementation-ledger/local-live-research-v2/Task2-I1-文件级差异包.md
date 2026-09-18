# Task 2 独立复核 I1 文件级差异包

状态：已实施并完成离线范围复验；负责人：Agent 端维护负责人；更新时间：2026-09-17。
适用范围：local_live 来源描述符的启用历史证据组合门。

本包使用实施前文件快照与当前文件做非 Git 审查。基线位于
`C:\Users\Administrator\AppData\Local\Temp\efficiency-platform-agent-task2-r2-i1-20260917210959`；
其中不含 `.env`、密钥或连接配置。

| 文件 | 文件级差异 | 边界 |
|---|---|---|
| `src/efficiency_platform_agent/configuration/research_local_sources.py` | 对 enabled 且 history 非 unknown 的来源，增加 `history_verified`、`freshness_sla`、`max_lookback` 三项合取校验，缺失时返回 `SOURCE_HISTORY_UNSUPPORTED` | 未修改通用 Registry、Admission 或 Provider |
| `tests/unit/configuration/test_research_local_sources.py` | 增加三种 history mode 乘三类缺失证据的九组负例，以及三种合法已核验历史正例；既有 admission fixture 显式满足新前置条件 | 负例在 build 前失败，不产生 reservation 或网络调用 |
| `docs/adr/ADR-0004-免费公开源本地实时V2研究运行模式.md` | 追加 Task 2 I1 裁决、适用模式和保留边界 | 不改变 ADR-0002/0003 |
| `docs/superpowers/plans/2026-09-17-免费公开源本地实时V2研究闭环-实施计划.md` | 在 Task 2 增加独立复核补强及验证矩阵；将含义不明的命令省略号改为明确模块占位说明 | 不进入 Task 3～9 |
| `docs/implementation-ledger/2026-09-17-免费公开源本地实时V2研究闭环-进度账本.md` | 更新状态并记录快照、红绿测试、质量门和未完成项 | 不宣称真实来源或生产验收 |

核心实现差异等价于：

```python
if (
    item.enabled
    and item.history_mode != "unknown"
    and (
        not item.admission.history_verified
        or item.freshness_sla is None
        or item.max_lookback is None
    )
):
    raise ValueError("SOURCE_HISTORY_UNSUPPORTED")
```

审查时应同时核对进度账本中的 RED `9 failed, 14 passed`、GREEN `23 passed`，以及扩大聚焦
`126 passed, 47 subtests passed`。这些均为离线证据，不代表端点刷新、服务启动或真实会话验收。

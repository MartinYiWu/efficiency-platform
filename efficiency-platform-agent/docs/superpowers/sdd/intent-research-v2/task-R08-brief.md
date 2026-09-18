# R08 质量门槛、覆盖矩阵与免费 API 来源任务简报

| 属性 | 内容 |
|---|---|
| 任务 | R08 |
| 状态 | 离线通过 |
| 依赖 | R07、R03 离线通过 |
| 范围 | Agent 侧 H1–H6 质量裁决、集合状态、arXiv/GDELT 离线适配契约与回放清单 |

## 不变量

1. 质量由代码从已验证过滤、文档、事件、Claim、Evidence、冲突与来源策略事实聚合；模型不能直接写 accepted/COMPLETE。
2. H1 相关/时间/用户条件，H2 可定位完整内容，H3 全 Claim 引用，H4 事件不重复，H5 unresolved 不冒充事实，H6 来源允许，任一失败即该事件不进入正式交付。
3. `exact N` 不足形成硬缺口；`at_most N` 有 1..N 可用事件即可；`best_effort` 达 minimum 且无其他硬缺口时，少于 target 不自动 PARTIAL。
4. required facets 按已接受 Claim 的 claim_key 覆盖；缺失形成可补采 gap，不用固定行业子类或来源数量替代。
5. NO_MATCHES 只允许在计划完整执行、至少有来源尝试、无关键失败/截断且历史覆盖 complete 时产生；全失败或历史 unknown 必须 FAILED。
6. 单一来源失败不覆盖其他已验证事件；已有足够合格事件时可 COMPLETE 并保留警告。
7. arXiv 区分 submitted/updated、只采元数据/摘要且明确 summary scope，不下载 PDF；GDELT 必须显式窗口并把 URL 仅作为待取正文线索。
8. arXiv/GDELT 即使离线 HTTP 契约通过，在许可、免费性、限额、历史能力和公网可用性逐项真实验收前仍 disabled/UNVERIFIED，不计入可用来源数。

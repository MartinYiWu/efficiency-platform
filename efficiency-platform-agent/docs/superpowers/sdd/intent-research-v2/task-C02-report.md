# C02 实施报告：V2 中立契约与公共测试夹具

## 状态

**离线实现完成，等待控制器质量审查。**

本任务只处理 C02；未启用网络、真实模型、数据库、共享 DDL、生产配置或 Git 操作。

## 交付文件

- `src/efficiency_platform_agent/contracts/intent_v2.py`
- `src/efficiency_platform_agent/contracts/temporal_v2.py`
- `src/efficiency_platform_agent/contracts/research_v2.py`
- `src/efficiency_platform_agent/contracts/research_sources_v2.py`
- `src/efficiency_platform_agent/contracts/research_evidence_v2.py`
- `src/efficiency_platform_agent/contracts/research_ports_v2.py`
- `tests/contracts/test_intent_v2.py`
- `tests/contracts/test_research_v2.py`
- `tests/support/intent_v2_cases.py`
- `tests/support/research_v2_cases.py`

## 已实现边界

- 所有新增 Pydantic 边界模型采用 `extra="forbid"`、`frozen=True`，并使用固定 schema/contract version。
- IntentFrame、CapabilityPlan 最多 8 个目标；依赖 ID 必须存在且通过 DFS 环检测。
- FieldValue 区分 unknown/null、explicit/inherited/default/derived 来源；显式来源必须有 Unicode 字符区间，默认/继承/派生必须带相应版本依据。
- ResolvedTimeWindow 只接受合法 IANA 时区、有时区 UTC 起止和正长度窗口。
- CountPolicy 校验 exact/at_most/best_effort、正数上下限及 minimum 不超过 target。
- ResearchBrief 使用受信任上下文承载身份和预算，模型传入 `tenant_id`/`budget_lease_id` 等额外字段会被拒绝；canonical digest 为排序 JSON SHA-256 且排除 diagnostics。
- 来源契约记录 cost/admission/history/content/rate，free_quota 必须可硬停止；文档、事件、Claim、EvidenceRef、覆盖率和质量契约分离。
- 14 个冻结中立 Protocol 已具备显式类型签名；无 `Any`、动态导入或 core/Pydantic 反向依赖。
- 显式 case registry 对未知 case_id 直接抛 `KeyError`，没有默认成功分支。

## 验证证据

执行目录：`efficiency-platform-agent`

```text
.venv/Scripts/python.exe -m pytest tests/contracts/test_intent_v2.py tests/contracts/test_research_v2.py -q
15 passed in 0.49s

.venv/Scripts/python.exe -m pytest tests/contracts/test_intent_v2.py tests/contracts/test_research_v2.py tests/architecture -q
58 passed, 124 subtests passed in 5.21s

.venv/Scripts/python.exe -m ruff check src/efficiency_platform_agent/contracts tests/contracts tests/support/intent_v2_cases.py tests/support/research_v2_cases.py
All checks passed!

.venv/Scripts/python.exe -m mypy <six new contract modules>
Success: no issues found in 6 source files
```

## 未宣称事项与风险

- 这是契约/夹具阶段，不代表意图解释、Reducer、真实时间解析、来源适配、SSRF、预算租约或 LangGraph 研究子图已经接通。
- 端口当前只有 Protocol，不包含运行时实现；C03 和 I01/R01 等后续任务必须继续复用这些类型，不能重新定义同名异构契约。
- 当前尚未进行真实来源许可/费用/可用性核验，仍遵循“只允许已验证免费或可硬停止免费配额”的后续准入门槛。

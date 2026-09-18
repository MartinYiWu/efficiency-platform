# R01 实施报告：来源目录、免费准入与策略配置

## 状态

**离线通过。**

本任务实现默认关闭的来源配置、显式 adapter 目录、免费准入、运行时范围/凭据/真实配额快照过滤及调用前账户级额度预留端口；未发起任何网络请求、未读取 Token、未启用真实来源，未修改 Java/UI/部署/共享 DDL，未执行 Git 操作。

## 交付文件

- `src/efficiency_platform_agent/configuration/research.py`
- `src/efficiency_platform_agent/configuration/__init__.py`
- `src/efficiency_platform_agent/contracts/research_sources_v2.py`
- `src/efficiency_platform_agent/capabilities/research/v2/__init__.py`
- `src/efficiency_platform_agent/capabilities/research/v2/source_admission.py`
- `src/efficiency_platform_agent/capabilities/research/v2/sources.py`
- `config/research_sources.toml`
- `config/research_policies.toml`
- R01 三组单元测试、任务简报及本报告/审查

## 已实现边界

- `SourceAdmission` 依次拒绝 disabled、准入记录漂移、UNVERIFIED/BLOCKED、Schema/权限未核验、未来/过期准入、paid/unknown、收费超额、缺失/未来/过期费用证据。
- 只有 `free` 或配置为 hard_stop 的 `free_quota` 能通过基础准入；free_quota 决策显式标记必须预留额度。
- `VerifiedSourceRegistry` 只接受显式 `registered_adapter_ids`，不动态导入模块；未知 adapter、用途未核验、凭据缺失、quota 未知/耗尽、用户/运行时来源限制、排除、primary、语言、地区、历史不足均在 Provider 前拒绝。
- 静态 `quota_limit` 不作为实时余额。可用性只消费可信账户级剩余额度快照；`reserve_for_call` 对 free_quota 强制调用注入的 `SourceQuotaLedger` 原子预留，没有账本或预留失败即不可调用。
- SourceRuntimeContext 新增可信 credential source IDs 与 quota remaining snapshot，禁止 naive now、重复/空范围和负额度。
- 配置 Schema `extra=forbid` 且 adapter 为封闭 Literal；`module_path` 或未知 adapter 无法加载。
- 检入的官方 Feed、GitHub Releases、HN 三个候选仅为 fixture 标识，全部 disabled、UNVERIFIED、unknown cost、无 Token/真实 URL；默认 Registry 可用来源为零。

## 验证证据

```text
R01 定向：15 passed
R01 + Research contracts + architecture：67 passed, 124 subtests passed
Intent/Conversation 离线回归：193 passed
Ruff：All checks passed
mypy：Success: no issues found in 6 source files
全量回归：1240 passed, 275 subtests passed, 2 existing dependency warnings in 39.98s
```

两条警告来自既有 Starlette 与 Polars 依赖，不由 R01 引入。

## 未宣称事项

- 本任务没有准入任何真实来源；官方条款、费用、Schema、历史覆盖与可用性需在 X04 逐源核验后形成 VERIFIED 记录。
- `SourceQuotaLedger` 仅冻结原子预留端口；真实账户级配额存储、恢复和结算归 R04/X01。
- URL/SSRF/DNS/重定向/字节上限属于 R02；通过 R01 不代表允许出网。

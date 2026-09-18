# C02 规格与质量审查

## 审查范围

依据 `task-C02-brief.md`、总计划 C02、两份相关设计和当前六个契约模块/四个测试支持文件进行文件级审查。项目 AGENTS.md 禁止 Git 操作，因此没有使用 diff/commit；以白名单文件、源码检查和测试输出作为证据。

## 规格审查

| 检查项 | 结果 | 证据 |
|---|---|---|
| 六个契约模块存在 | 通过 | `intent_v2.py`、`temporal_v2.py`、`research_v2.py`、`research_sources_v2.py`、`research_evidence_v2.py`、`research_ports_v2.py` |
| Intent/Research 测试与两个 support registry | 通过 | `tests/contracts/*_v2.py`、`tests/support/*_v2_cases.py` |
| extra forbid/frozen | 通过 | 所有边界模型继承 `_FrozenContract`；契约测试覆盖非法输入 |
| 时间、计数、目标 DAG、Unicode evidence/span | 通过 | 15 项契约测试覆盖；模型级 validator |
| unknown/null 与空集合分离 | 通过 | FieldValue、SourceConstraints、可选 tuple 字段 |
| 稳定摘要不含 diagnostics | 通过 | `ResearchBriefV2.canonical_digest()` 与测试 |
| 模型不能提交身份/预算 | 通过 | Brief 只接受 TrustedResearchContext；额外 `tenant_id`/`budget_lease_id` 被拒绝 |
| 14 个端口同步/异步签名 | 通过 | `research_ports_v2.py`，无 Any |
| V1 schema 未变 | 通过 | 固定 SHA-256 schema digest 测试 |
| 未知 fixture case 不默认成功 | 通过 | 两个 registry 的 `KeyError` 测试 |

## 质量审查

已执行：

- `pytest` 契约 + 架构：58 passed，124 subtests passed；
- `ruff check`：All checks passed；
- `mypy` 六个新契约模块：无问题；
- `compileall` 已在实现阶段通过；
- 读取检查未发现 `Any`、动态导入或从新契约反向导入 `core`。

## 结论

**C02 离线规格与质量通过。** 通过条件仅覆盖中立契约和离线夹具；C03 原子预算、I/R 实现与真实集成仍未完成，不能宣称 Agent 研究接口已可在线处理。

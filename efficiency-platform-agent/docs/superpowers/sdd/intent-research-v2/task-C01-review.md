# C01 规格与质量审查

| 属性 | 内容 |
|---|---|
| 状态 | 通过 |
| 审查人 | 主控制器；独立审查代理四次因模型容量或流断开失败，未使用其不完整输出 |
| 审查日期 | 2026-09-16 |
| 输入 | [任务简报](task-C01-brief.md)、[实施报告](task-C01-report.md)、当前文件、测试输出 |
| 审查方式 | 项目禁止 Git；按实施报告文件清单逐文件核对，并运行新鲜验证 |

## 规格符合性

结论：通过。

- `pyproject.toml` 已把 HTTPX 放入运行依赖，并声明 feedparser、Trafilatura、dateparser、tzdata；`uv.lock` 精确解析相关版本。
- `tests/governance/test_research_v2_dependency_admission.py` 仅使用内存 RSS/Atom、HTML 和显式基准日期，不执行网络、不读取配置。
- [依赖与开源准入记录](依赖与开源准入记录.md)记录版本、许可证、传递依赖、机制参考和复制限制。
- ADR-0002、三份设计、三份计划及两份旧选型已记录批准范围和局部替代；共享 DDL、真实来源、模型新增费用、部署、生产切换和 Java/UI 没有被扩大授权。
- [实施进度账本](实施进度账本.md)包含 25 个任务、基线、文件白名单、项目禁止 Git 的评审例外和未验证边界。

首次控制器审查发现六处旧时点文字仍写“待批准”或“实施冻结”，属于 Important 一致性问题。修复后再次搜索和文档测试，当前批准状态与 C01 事实一致；历史批准记录保留。

## 质量审查

结论：通过，带一项既有依赖风险。

- 准入测试具备真实解析断言，不以 import 成功替代全部行为；中文相对日期显式传入基准时间和时区。
- 运行依赖与开发依赖没有重复 HTTPX；锁文件由 uv 生成，未手工编辑。
- 没有业务代码、网络开关、Secret、数据库或 Runtime 架构改动。
- `uv audit --frozen` 对既有 `accelerate 1.14.0` 报 CVE-2026-69112 且暂无修复版本。该包不是 C01 新增依赖；风险保留在准入记录和实施报告中，后续由现有依赖所有者评估不可信 checkpoint 暴露面。不得据此宣称全量依赖安全扫描通过。

## 新鲜验证

```text
.venv/Scripts/python.exe -m pytest tests/governance/test_documentation_contract.py tests/governance/test_research_v2_dependency_admission.py -q
23 passed, 117 subtests passed in 5.15s

.venv/Scripts/python.exe -m pytest tests/orchestration tests/conversation tests/contracts tests/unit/capabilities/test_research_provider.py tests/unit/capabilities/test_research_contracts.py tests/architecture -q
172 passed, 133 subtests passed in 5.28s

uv lock --check
Resolved 229 packages in 1ms

.venv/Scripts/python.exe -m compileall -q src tests
退出码 0

.venv/Scripts/python.exe -m ruff check tests/governance/test_research_v2_dependency_admission.py
All checks passed
```

## 结论

C01 规格符合性通过、任务质量通过，可在账本标记为“离线通过”。这只关闭 C01，不代表 C02/C03、真实来源、真实模型、数据库、灰度或生产验收完成。

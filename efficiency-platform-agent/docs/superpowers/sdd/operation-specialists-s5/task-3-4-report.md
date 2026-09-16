# S5A Task 3+4 实施报告：研究与质量审校

## 本次范围

本次实现研究 Provider 唯一契约、Evidence Gate、研究洞察 Specialist、质量审校 Specialist 和有限修订决策，并补充固定 Fake 样本与离线测试。所有 Provider 均通过注入端口调用，未访问网络、模型、文件 Provider 或外部存储。

## 前置核验

实现开始时 S5 Task2 公共契约尚未落盘：

- `src/efficiency_platform_agent/agents/operation/definition.py`
- `src/efficiency_platform_agent/agents/operation/specialists/contracts.py`
- `src/efficiency_platform_agent/agents/operation/specialists/runtime.py`
- `tests/support/operation_specialist_fakes.py`

因此先按停止规则记录 RED，待 Task2 落盘后继续实现；未复制前置契约或修改 S1～S4。

## RED 证据

命令：

`$env:PYTHONPATH='src'; uv run python -m unittest tests.unit.capabilities.test_research_contracts tests.contract.capabilities.test_research_provider_contract tests.unit.agents.operation.quality.test_evidence_gate tests.unit.agents.operation.quality.test_revision tests.unit.agents.operation.specialists.test_research_quality tests.acceptance.test_operation_research_quality -v`

结果：退出码 1，4 个测试模块因目标契约/实现尚不存在而导入失败，失败原因分别指向 `capabilities.research.contracts` 和 `agents.operation.quality` 缺失；未以路径错误冒充功能通过。

## GREEN 证据

命令：

`$env:PYTHONPATH='src'; uv run python -m unittest tests.unit.capabilities.test_research_contracts tests.contract.capabilities.test_research_provider_contract tests.unit.agents.operation.quality.test_evidence_gate tests.unit.agents.operation.quality.test_revision -v`

结果：退出码 0，14 项测试通过，覆盖请求身份、版本、不可用失败、证据重复/结论关联、固定研究链、跨交付物冲突、预算不足和两轮修订上限。

## 已落盘文件

- `tests/fixtures/operation/research/industry_signal_v1.json`：两个不同发布者、两个固定结论的离线样本。
- `tests/fixtures/operation/quality/quality_review_script_v1.json`：ACCEPT、REVISE、QUALITY_NOT_MET 三种审校脚本样本。
- `tests/unit/capabilities/test_research_contracts.py`
- `tests/contract/capabilities/test_research_provider_contract.py`
- `tests/unit/agents/operation/quality/test_evidence_gate.py`
- `tests/unit/agents/operation/quality/test_revision.py`
- `tests/unit/agents/operation/specialists/test_research_quality.py`
- `tests/acceptance/test_operation_research_quality.py`
- `tests/unit/agents/operation/quality/__init__.py`
- `src/efficiency_platform_agent/capabilities/research/contracts.py`
- `src/efficiency_platform_agent/agents/operation/quality/evidence_gate.py`
- `src/efficiency_platform_agent/agents/operation/quality/revision.py`
- `src/efficiency_platform_agent/agents/operation/specialists/research.py`
- `src/efficiency_platform_agent/agents/operation/specialists/quality.py`
- `src/efficiency_platform_agent/prompts/resources/operation/research_insight_v1.j2`
- `src/efficiency_platform_agent/prompts/resources/operation/quality_review_v1.j2`

静态检查：相关源码和测试文件 `ruff check`、`ruff format --check` 与 `compileall` 已通过。

## 后续解阻条件

现有 S3 `QualityStatus` 未定义 `REVISE`，本实现使用 `FAILED` 表示需要修订，并由 `RevisionAction.REVISE` 对外表达修订动作；未越界修改 S3。当前验收仅验证固定 Fake 与确定性链路，研究 Agent 仍需后续接入完整 S4 输入解码和真实运行闭环。

## 未验证边界

尚未验证 Specialist 经 S4 SupervisorTask 的完整运行闭环、真实 S2 Model Runtime、真实公共搜索、网页原文、事实真实性、LLM 语义质量、S4 调度或生产端到端验收。

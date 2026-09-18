# R09 实施报告：有界补采 Planner 与唯一研究子图

## 状态

**离线通过。**

R09 已完成缺口驱动的补采动作提案边界、确定性 ActionValidator、稳定动作指纹、LangGraph Research V2 子图、连续无增益停止、终态优先级与受治理 replan Prompt。没有启用真实模型或来源、没有发起公网请求，未修改 Java/UI/部署/共享 DDL，未执行 Git 操作。

## 交付文件

- `src/efficiency_platform_agent/contracts/research_v2.py`
- `src/efficiency_platform_agent/orchestration/research_v2/__init__.py`
- `src/efficiency_platform_agent/orchestration/research_v2/planner.py`
- `src/efficiency_platform_agent/orchestration/research_v2/state.py`
- `src/efficiency_platform_agent/orchestration/research_v2/graph.py`
- `src/efficiency_platform_agent/prompts/registry.py`
- `src/efficiency_platform_agent/prompts/resources/research/replan_v2.j2`
- `tests/orchestration/research_v2/test_planner.py`
- `tests/orchestration/research_v2/test_graph.py`
- `tests/orchestration/research_v2/test_termination.py`
- `tests/unit/prompts/test_research_v2_templates.py`

## 已实现不变量

- 模型只可返回 `CollectionPlanV2` 候选；没有 gap 时程序直接返回 `QUALITY_MET`，模型返回 `RESEARCH_COMPLETE` 或 `QUALITY_MET` 会失败关闭。
- `ActionValidator` 逐动作重验已有 gap、允许的 action_kind、原 Brief 时间窗、唯一 requirement、来源准入、免费状态、来源角色、历史能力、预算与稳定指纹。
- `action_id` 由 intent revision、gap id/code、source、规范化 query 与 cursor 生成；已完成动作只记录为 rejected，不重复执行或重复收费。
- 动作顺序由程序确定：事实/时间/原始来源/冲突/来源阻断优先，required facet 次之，数量缺口再次，热度与格式缺口最后。
- Research 子图是现有 LangGraph Runtime 内的唯一受控子图，固定执行 validate、plan、discover、acquire、normalize、filter、deduplicate、cluster、claims、quality、compose、verify、render、finalize，不创建第二 Harness 或外部循环。
- GraphState 只保存 Brief/Policy/Budget 版本、动作/文档/事件/Claim/Evidence/Artifact ID、质量摘要与控制计数，不保存正文、HTML、Prompt 或模型自由文本。
- 初采不计 refill；补采最多两轮，连续两轮没有新增合格事件、Claim 或关闭 hard gap 时以 `NO_GAIN` 停止，并保留已有 evidence/claim/event ID。
- 取消、致命错误和硬截止优先于质量终态；软截止/预算优先于无增益与轮次；`COMPLETE` 必须走完 compose、verify、render 且 `output_verified=true`。
- `research.v2.replan@1.0.0` 明确要求唯一 ContextBuilder、USER_UNTRUSTED 数据边界、原范围不扩张、只选已准入免费来源，并禁止模型宣布完成。

## 验证证据

```text
R09 定向：uv run python -m pytest tests/orchestration/research_v2 tests/unit/prompts/test_research_v2_templates.py -q
结果：19 passed

全量离线回归：uv run python -m pytest -m "not real_external" -q
结果：1416 passed, 275 subtests passed, 2 warnings in 46.21s

Ruff 规则：uv run python -m ruff check src tests scripts
结果：All checks passed

R09 格式：uv run python -m ruff format --check <R09 的 9 个 Python 文件/目录>
结果：9 files already formatted

mypy：uv run python -m mypy src/efficiency_platform_agent
结果：Success: no issues found in 262 source files

compileall：uv run python -m compileall -q src tests scripts
结果：退出码 0

治理与架构：uv run python -m pytest tests/governance/test_documentation_contract.py tests/architecture -q
结果：62 passed, 241 subtests passed
```

两条警告仍来自既有 Starlette BlockingPortal 弃用提示与 Polars 未来返回类型提示，不由 R09 引入。

## 环境与边界

- 当前工作区由旧路径迁移而来，`.venv/Scripts/pytest.exe` 启动器仍指向旧目录；直接 `uv run pytest` 会错误复用旧环境。验证统一使用 `uv run python -m pytest`，当前解释器与依赖已通过 `uv sync --all-groups --locked` 核对。
- 全仓 `ruff format --check src tests scripts` 当前报告 84 个历史格式漂移文件；R09 未批量改写这些用户既有文件，R09 触达的 9 个 Python 目标已单独通过格式检查，且全仓 Ruff 规则检查通过。
- R09 只提供端口、状态机与离线假 Runner 验证；ModelRuntime、ContextBuilder、Tool Runtime、真实存储与正式 Supervisor 的组合根接线属于 X02/X03，真实模型与来源验收属于 X04/X05。

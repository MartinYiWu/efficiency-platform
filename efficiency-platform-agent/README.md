# Efficiency Platform Agent

纯 Agent 侧工程，承载统一 Agent Harness、混合执行策略、未来多 Agent 协作以及模型、工具、知识、文档、OCR、分析等技术能力。

当前已完成 S2～S7 的离线底座、统一执行主链、多 Agent Supervisor、运营 Specialist、Scenario Pack 和真实验收控制面；不包含 Java 侧架构与部署设计，也未执行真实外部 Gate。

## 当前架构候选基线

以下为当前架构和技术组件基线；这不代表运行依赖、真实模型或外部基础设施已经连接或完成验收：

- 总体范式：Harnessed Hybrid Multi-Agent Architecture
- 编排拓扑：统一 Graph Runtime + 中央 Supervisor + 专家 Agent 子图
- 执行策略：Direct、Workflow、ReAct、Plan-and-Execute、Multi-Agent
- 扩展方式：Agent、Strategy、Tool、Capability、Provider 均通过稳定端口接入
- 运行治理：统一状态机、上下文、权限、预算、超时、取消与 Checkpoint；P1 仅保留结构化日志和关联接口，完整可观测与评测后置

完整说明见：

- [S1～S7 阶段实施总览](docs/superpowers/sdd/阶段实施总览.md)
- [纯 Agent 侧总体架构](docs/architecture/纯Agent侧总体架构.md)
- [扩展开发约定](docs/architecture/扩展开发约定.md)
- [Agent 侧技术组件选型](docs/architecture/Agent侧技术组件选型.md)
- [ADR-0001 自适应模型策略路由](docs/adr/ADR-0001-自适应模型策略路由.md)
- [P1 Agent Runtime 技术组件选型设计](docs/superpowers/specs/2026-09-02-P1-Agent-Runtime技术组件选型-设计.md)
- [P2 Provider 与 RAG 技术组件选型设计](docs/superpowers/specs/2026-09-02-P2-Provider与RAG技术组件选型-设计.md)
- [P3 文档解析与 OCR 技术组件选型](docs/superpowers/specs/2026-09-02-P3-文档解析与OCR-技术选型.md)
- [P4 公共研究与数据分析技术组件选型](docs/superpowers/specs/2026-09-02-P4-公共研究与数据分析-技术选型.md)
- [P5 MCP、评测与基础质量保障技术组件选型](docs/superpowers/specs/2026-09-02-P5-MCP评测与基础质量保障-技术选型.md)
- [P1 Agent Runtime 实施规划参考（已冻结、不可执行）](docs/superpowers/plans/2026-09-02-P1-Agent-Runtime实施计划.md)

## 开发规范

- [仓库强制规则](AGENTS.md)
- [Agent 侧开发总纲](Agent.md)
- [贡献与交付流程](CONTRIBUTING.md)
- [安全基线](SECURITY.md)
- [工程规范索引](docs/standards/00-规范索引.md)
- [文档模板](docs/templates/)
- [SQL 变更规范](sql/README.md)

## LLM 与基础设施本机配置

- `config/llm-routing.toml` 是可提交的非敏感路由配置：当前注册 `deepseek_direct`，并预留禁用的未来 `model_pool`；候选模型由 Harness 按 Agent 需求、健康度、预算和能力动态选择，不是固定调用顺序。
- `.env.example` 是可提交的变量清单，所有值为空；项目根 `.env` 被忽略，仅保存本机受控配置，禁止提交、复制到文档、日志或测试。
- 本机 `.env` 的真实值由项目负责人自行维护；本项目只校验键名、结构和启用状态，不读取、输出或记录 Secret 值。模型池仍保留为后续配置项。
- 配置文件与 Provider 适配器已完成离线契约实现，不代表真实模型、数据库、Redis、COS 或 DashScope 已完成连接和验收。

## 当前验证

```powershell
uv run pytest -m "not real_external" -q
uv run python -m unittest discover -s tests -p "test_*.py" -q
uv run ruff check src tests scripts
uv run mypy src/efficiency_platform_agent
uv run python -m compileall -q src tests scripts
```

当前第三方依赖已在 `pyproject.toml` 和 `uv.lock` 中锁定；真实外部连接、跨进程持久化和生产验收必须按 S7 授权流程单独执行。

## VSCode 本地启动与调试

仓库已提供 `.vscode/settings.json` 和 `.vscode/launch.json`：测试发现范围固定为 `tests`，启用 pytest 并关闭 unittest。按 F5 可选择以下配置：

- `启动：本地真实 Agent API`：通过 `efficiency_platform_agent` 模块启动本地 API，使用集成终端；本机 `.env` 只由启动入口读取，配置文件不保存其中的值。
- `调试：当前 pytest 测试文件`：调试当前编辑器中的 pytest 文件。
- `调试：Agent 全量离线测试`：运行 `tests` 并排除 `real_external` 标记的测试。

停止调试请使用 VSCode 的停止按钮或集成终端的 `Ctrl+C`。真实模型、数据库、Redis、COS 等外部连接仍须按授权流程单独验收。

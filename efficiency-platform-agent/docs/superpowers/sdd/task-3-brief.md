### Task 3: 落地规范索引、工程、架构、Python 和测试规范

**Files:**

- Create: `docs/standards/00-规范索引.md`
- Create: `docs/standards/01-工程与目录规范.md`
- Create: `docs/standards/02-架构与依赖规范.md`
- Create: `docs/standards/03-Python编码与注释规范.md`
- Create: `docs/standards/04-测试与质量门禁.md`

**Interfaces:**

- Consumes: `AGENTS.md` 规则等级、`Agent.md` 架构边界、已批准规范体系设计
- Produces: 工程开发和代码评审直接引用的详细规范前半部分

#### Step 1: 编写 00-规范索引.md

必须包含：适用范围；MUST/MUST NOT/SHOULD/MAY 规则等级；规则优先级；适用角色；`01` 至 `09` 九份规范导航；五份模板导航；常见任务路由；规范修改与例外流程。所有链接必须使用相对 Markdown 链接：

- 同目录规范：例如 `[工程与目录规范](01-工程与目录规范.md)`；
- 模板：例如 `[架构设计文档模板](../templates/架构设计文档模板.md)`。

后续任务尚未创建的规范和模板链接允许暂时不可达，但链接目标必须准确。

#### Step 2: 编写 01-工程与目录规范.md

必须详细定义：

- `src/efficiency_platform_agent` 布局与每个一级包职责；
- `tests/architecture`、`tests/governance` 和后续单元/契约/集成/验收布局；
- `docs/architecture`、`docs/standards`、`docs/templates`、`docs/superpowers` 职责；
- `sql/changes` 布局；
- 配置只通过 `pyproject.toml`、环境变量、配置对象，不将密钥落库或入仓；
- 包/模块/测试/配置/资源文件命名；
- 禁止建立无所有权的 `common`、`utils`、`misc` 收容层；
- Provider、Capability、Tool、Core 等通用代码的真实归属；
- 依赖声明与 `uv.lock` 目标；
- 生成文件、缓存和敏感文件；
- 新增顶层目录或跨层模块必须先更新设计或 ADR。

#### Step 3: 编写 02-架构与依赖规范.md

必须定义依赖方向：

```text
API → Harness → Routing / Orchestration → Strategies / Agents / Workflows
                                            ↓
                   Context / Memory / Tools / Capabilities
                                            ↓
                         Providers / Persistence
                                            ↓
                              Core / Contracts
```

必须详细说明每层允许职责和禁止职责；`core` 不依赖上层；内部层不依赖 `api`；Provider/Persistence 不依赖执行层；Agent 不实例化厂商 SDK；Graph Runtime 唯一；Strategy Router 与 Supervisor 分工；专家 Agent 不点对点自由调用；什么变更必须 ADR。列出当前验证命令：

```powershell
python -m unittest tests.architecture.test_dependency_rules -v
```

#### Step 4: 编写 03-Python编码与注释规范.md

必须详细定义：

- Python 3.12 目标基线，同时说明当前骨架可由 Python 3.11 验证，第三方依赖锁定前不得宣称 3.12 兼容性已验收；
- 包、模块、类、Protocol、函数、变量、常量、枚举命名；
- 全部公共边界类型标注；Protocol、frozen/slots dataclass、StrEnum 的适用场景；
- async 边界、阻塞 I/O 隔离、连接池、显式超时、取消传播、上下文管理器；
- 领域错误、Provider 错误、Tool 错误、输入错误与禁止吞异常；
- import 顺序、绝对/相对导入和循环依赖；
- Docstring 必填对象；
- 行内注释解释原因、不变量、边界和风险，不逐行翻译代码；
- Graph Node Docstring：输入状态、输出更新、副作用、暂停点、幂等、异常；
- Tool Docstring：参数、权限、副作用、超时、重试、返回；
- Provider Docstring：厂商映射、超时、错误归一化、降级；
- 待办标记必须有任务编号或负责人及移除条件；
- 禁止注释掉的死代码、密钥、个人信息和完整 Prompt；
- 结构化日志字段包含 `run_id`、`trace_id`、`tenant_id` 等，敏感值不得记录。

必须提供：一个合规 Graph Node Docstring 示例、一个合规 Tool Docstring 示例、至少一组坏注释/好注释对比。代码标识符英文；中文注释允许保留标准英文技术术语；同一模块风格一致。

#### Step 5: 编写 04-测试与质量门禁.md

必须详细定义：单元、契约、架构、Graph、Provider 集成、RAG/OCR 固定数据集、安全和验收测试；TDD 的 RED/GREEN/REFACTOR；Mock 仅位于外部边界；非确定性输出的结构/属性/固定样本验证；失败与噪声处理；当前门禁与目标门禁；完成证据格式。

当前真实门禁：

```powershell
python -m unittest discover -s tests -v
python -m compileall -q src
```

当前 AST 依赖守卫也必须列出。pytest、pytest-asyncio、Ruff、mypy、respx、Hypothesis、Ragas、Locust 只能标为组件引入后的目标门禁，不得声称已安装或已执行。

#### Step 6: 验证

运行：

```powershell
python -m unittest tests.architecture.test_dependency_rules -v
python -m unittest tests.governance.test_documentation_contract.DocumentationContractTest.test_agents_rules_link_to_detailed_standards tests.governance.test_documentation_contract.DocumentationContractTest.test_agent_handbook_preserves_selected_architecture -v
python -m unittest discover -s tests -v
```

Expected：架构依赖测试 PASS；两个根文档契约 PASS；完整测试仍可因 Task 4-6 尚未创建的文档保持 RED，但不得出现现有架构测试回归或本任务已创建文件缺失。报告须列出准确 failure/error 数和剩余缺失文件。

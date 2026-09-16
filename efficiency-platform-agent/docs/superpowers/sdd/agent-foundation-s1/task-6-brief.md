### Task 6: 固化扩展文档、架构门禁和阶段交付证据

**Files:**
- Modify: `docs/architecture/扩展开发约定.md`
- Modify: `docs/standards/06-Agent-Prompt-Tool开发规范.md`
- Modify: `docs/superpowers/plans/2026-09-03-Agent快速构建底座-实施计划.md`
- Create: `docs/superpowers/sdd/agent-foundation-s1/进度账本.md`
- Modify: `tests/governance/test_documentation_contract.py`
- Modify: `tests/architecture/test_core_contracts.py`

**Interfaces:**
- Consumes: S1 已实现的公共接口和测试证据。
- Produces: 可发现的 Agent 接入步骤、中文契约说明、架构守卫和阶段评审包。

- [ ] **Step 1: 编写文档契约失败测试**

增加断言，要求扩展文档明确包含以下稳定入口：

```text
AgentSpec
AgentValidator
AgentRegistry
AgentFactory
CapabilityRequirement
显式注册
禁止动态导入和注册副作用
```

同时扩展核心契约测试，确认 `core/agent.py` 不引用 `agents`、Provider、Harness 或 LangGraph。

- [ ] **Step 2: 运行治理和架构测试并确认失败**

Run:

```powershell
uv run python -m unittest tests.governance.test_documentation_contract tests.architecture.test_core_contracts tests.architecture.test_dependency_rules -v
```

Expected: FAIL，指出扩展文档尚未记录 S1 接入流程或新增架构断言尚未满足。

- [ ] **Step 3: 更新扩展文档**

文档必须给出新 Agent 的确定顺序：

```text
定义 AgentSpec
→ 定义稳定输入输出 Schema
→ 实现 AgentPlugin
→ AgentValidator 本地校验
→ AgentRegistry 显式注册
→ AgentFactory 装配
→ 运行准入契约测试
→ 才能被 Supervisor 按能力匹配
```

明确禁止业务 Agent 修改 Harness/Graph Runtime 公共生命周期、直接调用 Provider SDK、动态扫描插件和通过 `__init__.py` 导入副作用注册。

- [ ] **Step 4: 建立进度账本**

`docs/superpowers/sdd/agent-foundation-s1/进度账本.md` 必须包含：

- 任务 1～6 状态；
- 每个任务实际修改文件；
- 红灯与绿灯测试命令和结果；
- 评审意见及修复；
- 未验证项；
- 下一阶段可依赖接口；
- 项目无 Git，使用文件快照和测试证据的说明。

- [ ] **Step 5: 运行完整离线回归**

Run:

```powershell
uv run python -m unittest discover -s tests -p "test_*.py" -v
```

Expected: PASS，零失败、零错误；架构、治理、配置和全部 S1 测试同时通过。

- [ ] **Step 6: 编译全部 Python 源码**

Run:

```powershell
uv run python -m compileall -q src tests
```

Expected: exit code 0，无语法错误。

- [ ] **Step 7: 执行敏感信息和英文注释复核**

检查新增文件不含 API Key、Authorization、连接串、真实业务数据或英文 Docstring；标识符和标准技术术语不视为违规。发现问题必须修复后重新运行完整回归。

- [ ] **Step 8: 更新计划实际状态并形成阶段交付报告**

逐项勾选真实完成步骤，禁止提前勾选。交付报告必须区分：

- 已实现：S1 Agent 定义、校验、显式注册、匹配和装配；
- 已验证：实际通过的离线命令和测试数量；
- 未实现：Harness、LangGraph、真实 Provider、运营领域模型和业务 Specialist；
- 未验证：真实模型、网络、数据库、Redis、COS、Windows/Linux 生产兼容；
- 下一步：为 S2 统一执行主链编写独立详细计划。

## 2. S1 完成门禁

只有同时满足以下条件，S1 才能标记完成：

1. AgentSpec 能完整表达 Agent 类型、能力、任务、Schema、策略、Prompt、工具、知识、记忆、模型、质量、权限和终止条件。
2. AgentValidator 对缺失、冲突和实例不一致失败关闭。
3. AgentRegistry 使用显式注册并提供稳定能力匹配；不存在动态导入或注册副作用。
4. AgentFactory 对 Builder 失败和非法实例安全归一化。
5. 合成 Specialist 能通过 Registry → Factory → AgentPlugin.run 完成确定性契约测试。
6. 新接口不改变 Harness、Graph Runtime、Run 状态机、Tool 或 Provider 语义。
7. 全部测试和 compileall 使用 Python 3.13/uv 新鲜通过。
8. 新增注释和 Docstring 使用中文，敏感信息检查无发现。
9. 文档、进度账本、文件清单和未验证边界同步完成。

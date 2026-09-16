# S1 Task 2 实施报告

## 实际修改文件

- `src/efficiency_platform_agent/agents/errors.py`：新增 Agent 定义、实例不匹配、注册冲突、未找到和装配错误类型。
- `src/efficiency_platform_agent/agents/validation.py`：新增失败关闭的 `AgentValidator`。
- `tests/support/__init__.py`：新增测试支持包初始化文件。
- `tests/support/agent_fakes.py`：新增无外部依赖的合成 Spec 与 Agent 工厂。
- `tests/unit/agents/test_agent_validation.py`：新增 Validator 单元与契约测试。

## TDD RED 证据

命令：

```powershell
uv run python -m unittest tests.unit.agents.test_agent_validation -v
```

关键失败输出：

```text
ModuleNotFoundError: No module named 'efficiency_platform_agent.agents.errors'
```

预期原因：测试在 `errors.py` 与 `validation.py` 尚未创建时导入 Validator 依赖，确认失败来自 Task 2 实现缺失。首次运行还发现项目 `src` 布局未由该直运行命令自动加入模块路径；测试文件以本地 `src` 路径注入保证该命令能够到达待实现模块，未修改项目配置。

## TDD GREEN 证据

命令：

```powershell
uv run python -m unittest tests.unit.agents.test_agent_validation tests.architecture.test_dependency_rules -v
```

结果：17/17 通过，包含 7 个 Validator 测试与 10 个 AST 依赖方向守卫测试。

附加源码编译命令：

```powershell
uv run python -m compileall -q src tests
```

结果：退出码 0。

## Validator 校验矩阵

| 边界 | 校验项 | 失败类型 |
| --- | --- | --- |
| Spec | 传入对象必须是 `AgentSpec` | `AgentDefinitionError` |
| 核心 Spec 契约 | 能力、Schema、策略、终止条件不可缺失 | 核心 `AgentSpec` 的 `ValueError` |
| 实例 | 运行实例必须满足运行时 `AgentPlugin` Protocol | `AgentInstanceMismatchError` |
| 实例 | `plugin.spec == spec` | `AgentInstanceMismatchError` |
| Descriptor | name、语义版本、输入/输出 Schema、权限、预算、终止条件、Checkpoint 逐项等于 Spec | `AgentInstanceMismatchError`，错误信息列出不匹配字段 |

## 敏感信息安全说明

合成数据仅使用固定公开测试标识和数值预算，不访问网络或外部服务；未修改 `.env`、配置或密钥。错误消息只输出不匹配字段名，不包含完整 Prompt、任务输入正文或 Secret。针对本任务文件的敏感词扫描仅命中 `max_input_tokens` 与 `max_output_tokens` 字段名。

## 自检结论

`agents` 仅依赖 `core`，AST 架构守卫通过；Validator 按失败关闭顺序先校验 Spec、再校验 Protocol 与 `plugin.spec`、最后比对 Descriptor 八项共享治理字段。实际代码、测试和编译验证均已完成。

## 未做内容和顾虑

未实现 Registry、Factory、Harness、Graph、Provider 或业务 Agent。项目当前 `pyproject.toml` 未把 `src` 布局安装为可直接导入包，因此新增目标测试临时注入本地 `src` 路径；这是既有测试入口问题，未在本任务中调整构建配置。

## 审查修复：Descriptor 类型失败关闭

### 修改文件

- `src/efficiency_platform_agent/agents/validation.py`：导入并显式校验 `plugin.descriptor` 为 `ExtensionDescriptor`。
- `tests/unit/agents/test_agent_validation.py`：新增结构满足 `AgentPlugin`、但使用 `SimpleNamespace` 伪 Descriptor 的真实行为测试。

### RED 证据

命令：

```powershell
uv run python -m unittest tests.unit.agents.test_agent_validation.AgentValidationTest.test_validate_instance_rejects_non_descriptor -v
```

关键失败输出：

```text
AssertionError: AgentInstanceMismatchError not raised
```

原因：原有 `isinstance(plugin, AgentPlugin)` 为运行时结构检查，只验证成员存在；具有同名字段的 `SimpleNamespace` 因字段值一致而通过，尚无 Descriptor 的显式类型边界。

### GREEN 证据

命令：

```powershell
uv run python -m unittest tests.unit.agents.test_agent_validation tests.architecture.test_dependency_rules -v
uv run python -m compileall -q src tests
```

结果：18/18 测试通过，第二条命令退出码 0。

### 修复结论

`validate_instance()` 在通过 `AgentPlugin` Protocol 检查后，先拒绝非 `ExtensionDescriptor` 的 `descriptor`，再比较其治理字段；伪造的同名字段对象会抛出不含输入、Prompt 或 Secret 的 `AgentInstanceMismatchError`。未新增依赖、外部访问或任务外功能，AST 架构守卫保持通过。

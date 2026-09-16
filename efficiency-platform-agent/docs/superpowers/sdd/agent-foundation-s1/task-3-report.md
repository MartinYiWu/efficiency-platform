# S1 Task 3：显式 Agent Registry 和能力匹配评审报告

| 属性 | 内容 |
|---|---|
| 状态 | 已完成并已验证 |
| 负责人 | Codex |
| 更新时间 | 2026-09-03 |
| 适用范围 | S1 Task 3 的显式注册、查找、能力匹配与快照 |
| 不适用范围 | Factory、Harness、Graph、Provider、业务 Agent |

## 实际变更文件

| 文件 | 变更 |
|---|---|
| `src/efficiency_platform_agent/agents/registry.py` | 新增 `AgentBuilder`、不可变 `RegisteredAgent` 和显式 `AgentRegistry`。 |
| `tests/unit/agents/test_agent_registry.py` | 新增 7 个离线 `unittest` 行为测试。 |
| `docs/superpowers/sdd/agent-foundation-s1/task-3-report.md` | 新增本评审证据。 |

## TDD 证据

### RED

先新增 Registry 测试，再执行：

```powershell
uv run python -m unittest tests.unit.agents.test_agent_registry -v
```

实际结果为失败，且在补齐既有测试模式所需的 `src` 路径引导后，失败原因准确为目标模块尚未实现：

```text
ModuleNotFoundError: No module named 'efficiency_platform_agent.agents.registry'
Ran 1 test in 0.000s
FAILED (errors=1)
```

### GREEN

完成最小实现后执行：

```powershell
uv run python -m unittest tests.unit.agents.test_agent_registry tests.architecture.test_dependency_rules -v
```

实际结果：

```text
Ran 17 tests in 0.548s
OK
```

交付前再次执行编译、同一测试集合和禁止机制扫描：

```powershell
uv run python -m compileall -q src tests
uv run python -m unittest tests.unit.agents.test_agent_registry tests.architecture.test_dependency_rules -v
rg -n -i "importlib|pkgutil|os\.walk|pathlib\.Path\(.*glob|\.glob\(|environ|dotenv|load_dotenv" src\efficiency_platform_agent\agents\registry.py
```

实际结果：编译命令退出码为 0；测试输出为 `Ran 17 tests in 0.483s` 和 `OK`；禁止机制扫描无命中。

## 注册与匹配行为矩阵

| 场景 | 输入/条件 | 结果 | 自动化证据 |
|---|---|---|---|
| 显式注册 | 有效 `AgentSpec` 和可调用 Builder | 保存 `RegisteredAgent`，不实例化 Agent | 所有注册相关测试 |
| 重复 ID | 再次注册相同 `agent_id` | 抛出 `AgentRegistrationConflictError`，原注册不覆盖 | `test_duplicate_agent_id_fails_closed` |
| 不存在 ID | `get("missing_agent")` | 抛出 `AgentNotFoundError` | `test_get_raises_for_an_unregistered_agent_id` |
| `all_of` | 候选缺少任一必需能力 | 不匹配 | `test_match_returns_an_empty_tuple_when_no_capability_matches` |
| `any_of` | `any_of` 非空且候选至少有一个能力 | 匹配 | `test_match_requires_all_capabilities_and_one_optional_capability` |
| `all_of` + `any_of` | 必需能力全满足且可选集合命中至少一个 | 匹配 | `test_match_requires_all_capabilities_and_one_optional_capability` |
| 类型筛选 | 指定 `kind` | 仅返回同一 `AgentKind` 的项 | `test_match_can_filter_by_agent_kind` |
| 稳定排序 | 注册顺序为 `agent_b` 后 `agent_a` | 按 `agent_id` 返回 `agent_a`、`agent_b` | `test_match_requires_all_capabilities_and_one_optional_capability` |
| 无匹配 | 无候选满足能力 | 返回空元组，由调用方决定错误处理 | `test_match_returns_an_empty_tuple_when_no_capability_matches` |
| 快照 | 获取后继续注册或尝试赋值 | 原快照不变，赋值抛出 `TypeError` | `test_snapshot_is_an_immutable_copy_of_current_registrations` |
| Builder 失败关闭 | Builder 不可调用 | 注册前抛出 `TypeError` | `test_register_rejects_a_non_callable_builder` |

## 自检

- 使用普通字典进行唯一 ID 的显式注册；没有动态导入、目录扫描、包导入副作用或环境变量覆盖。
- `register()` 仅校验 `AgentSpec` 和 Builder 可调用性，不执行 Builder；因此不触发业务 Agent 或外部服务。
- `snapshot()` 基于字典副本创建 `MappingProxyType`，既不可修改，也不会随后续注册改变。
- `match()` 同时满足 `all_of` 全包含、非空 `any_of` 至少一个命中，以及可选 `kind` 相同；返回按 `agent_id` 排序的元组。
- 未执行 Git 命令；未改动密钥、配置或外部服务。

## 未做内容与顾虑

- 未实现且未声称实现 Factory、实例装配/验证、Harness、Graph、Provider、业务 Agent 或隐式自动发现；这些属于后续任务。
- 仅运行了本任务的 Registry 单元测试、AST 依赖守卫和 `compileall`；未运行项目全量测试，也未运行尚未配置为当前门禁的 Ruff、mypy、pytest 或依赖安全扫描。
- 当前 `AgentSpec` 的不可变性由其既有冻结数据类承担；本任务只保证注册表容器的快照不可修改。

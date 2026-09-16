# S1 文档门禁修复报告

## 范围

增强 `tests/governance/test_documentation_contract.py` 的 S1 文档门禁，同时校验：

- `docs/architecture/扩展开发约定.md`
- `docs/standards/06-Agent-Prompt-Tool开发规范.md`

两份文档均须明确稳定入口、显式注册、禁止动态导入，以及禁止通过注册副作用接入。

## RED

先新增双文档统一字面量断言，要求包含“稳定入口”“显式注册”“动态导入”“注册副作用”。运行：

```powershell
python -m unittest tests.governance.test_documentation_contract.DocumentationContractTest.test_s1_entry_contract_is_explicit_in_architecture_and_standard_documents -v
```

结果：失败（2 个子测试），原因是现有文档分别使用“稳定能力匹配”和“稳定端口”表达稳定入口，没有统一使用“稳定入口”字面量。

## GREEN

将断言收敛为正则语义门禁：稳定入口接受“稳定端口”或“稳定能力匹配”；其余三项仍要求明确字面量。新增中文注释说明该兼容表达范围。

目标测试结果：`Ran 1 test ... OK`。

完整治理测试：

```powershell
python -m unittest tests.governance.test_documentation_contract -v
```

结果：`Ran 17 tests ... OK`。

## 变更边界

未修改文档内容或生产代码；测试变更仅增加双文档 S1 入口/注册禁令覆盖，报告为本任务要求的证据文件。

## 复审加固：RED

将原先仅覆盖架构文档的五个 S1 接口标识收紧为两份权威文档逐份校验：
`AgentSpec`、`AgentValidator`、`AgentRegistry`、`AgentFactory`、`CapabilityRequirement`。
同时逐份校验显式注册、动态导入和注册副作用禁令。

使用内存变异移除标准 06 文档中的 `AgentFactory` 后运行断言，得到：
`AssertionError: S1 gate must fail when standard 06 misses AgentFactory`。
该 RED 证明标准 06 缺少任一接口时门禁会失败；源文档未被修改。

## 复审加固：GREEN

最小实现为将既有门禁的文档集合扩展为架构文档与标准 06 文档，并对每份文档逐项执行八个标记断言。

```powershell
python -m unittest tests.governance.test_documentation_contract.DocumentationContractTest.test_extension_convention_documents_stable_s1_entry_points_and_registration_prohibitions -v
python -m unittest tests.governance.test_documentation_contract -v
```

结果分别为目标测试 `Ran 1 test ... OK`，完整治理测试 `Ran 17 tests ... OK`。

## 最终复审：行为条目禁令加固

架构文档禁令模式已收紧为实际行为条目，而不是仅匹配“必须明确禁止”元句：

- `接入过程禁止以下行为：[\\s\\S]{0,200}- 动态扫描、动态导入插件或动态注册；`
- `接入过程禁止以下行为：[\\s\\S]{0,250}- 通过 \`__init__\\.py\` 导入副作用完成注册；`

标准 06 使用实际同句 `MUST NOT` 禁令：

- `MUST NOT 动态扫描或动态导入插件`
- `MUST NOT 通过 \`__init__\\.py\` 导入副作用完成注册`

### 四类内存变异 RED

未写回文件，仅在内存中分别将架构文档和标准 06 文档的动态导入、注册副作用具体禁令改为“允许/MAY”。四类变异均被拒绝：

```text
架构-动态导入: rejected
架构-注册副作用: rejected
标准06-动态导入: rejected
标准06-注册副作用: rejected
```

### GREEN

目标 S1 门禁测试 `Ran 1 test ... OK`；完整治理测试 `Ran 17 tests ... OK`。

## 二次复审：禁止语义加固

仅检查“动态导入”和“注册副作用”词语不足以阻止文档写成允许语义。因此门禁新增逐文档禁止语义断言：目标行为前必须出现“必须明确禁止”“MUST NOT”或“不得”等禁止措辞，并保留行为词距离上限，避免跨段误匹配。

### RED

对标准 06 文档仅在内存中将 `MUST NOT` 替换为 `MAY`、将“必须明确禁止/不得”替换为允许语义，再检查动态导入禁止正则；断言失败并输出：
`AssertionError: S1 gate must fail when standard 06 allows dynamic import`。
源文档未被修改。

### GREEN

新增两条禁止语义正则，并对架构文档与标准 06 文档逐份执行：

- 禁止动态导入；
- 禁止注册副作用或通过导入副作用完成注册。

目标测试 `Ran 1 test ... OK`；完整治理测试 `Ran 17 tests ... OK`。

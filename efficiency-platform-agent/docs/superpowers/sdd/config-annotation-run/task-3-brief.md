### Task 3: 固化工程约束并执行全量验证

**Files:**
- Modify: `D:\efficiency-platform\efficiency-platform-agent\AGENTS.md`
- Modify: `D:\efficiency-platform\efficiency-platform-agent\docs\standards\01-工程与目录规范.md`
- Modify: `D:\efficiency-platform\efficiency-platform-agent\docs\standards\03-Python编码与注释规范.md`
- Modify: `D:\efficiency-platform\efficiency-platform-agent\tests\config\test_llm_configuration_template.py`
- Modify: `D:\efficiency-platform\efficiency-platform-agent\tests\governance\test_documentation_contract.py`
- Modify: `D:\efficiency-platform\efficiency-platform-agent\docs\superpowers\plans\2026-09-02-中文注释与DeepSeek默认配置-实施计划.md`

**Interfaces:**
- Consumes: Task 1/2 的结构验证和已批准设计。
- Produces: 可执行的中文注释/配置说明规范、通过的全量测试和已完成状态的实施记录。

- [ ] **Step 1: 收紧工程与编码规范**

在 `AGENTS.md` 的开发工作流章节增加项目级约束：本项目永久不是 Git 仓库，MUST NOT 要求、执行或声称 Git 初始化、提交、分支、推送、Git diff 或基于 Git 的审查流程；变更审查使用文件快照、文件级差异包和项目内进度账本。

在 `01-工程与目录规范.md` 的配置章节写入以下等价条款：

```markdown
- 每个项目自维护且支持注释语法的有效配置项 MUST 具有紧邻上方的中文说明；说明 MUST 覆盖用途，必要时覆盖格式、单位、敏感性、默认值、启用条件或缺失行为。注释 MUST NOT 包含真实 Secret。
- 不支持注释语法或由工具自动生成的配置文件 MUST NOT 人工插入注释；其配置项说明 MUST 写入紧邻的人工维护配置、Schema 或说明文档。
```

在 `03-Python编码与注释规范.md` 将“中文 Docstring 和注释 MAY”收紧为“项目自行编写的 Python Docstring 和注释 MUST 使用中文”，并保留英文标识符和标准技术术语的例外说明。

- [ ] **Step 2: 扩展规范测试的稳定断言**

如果 `tests/governance/test_documentation_contract.py` 已存在规范文本断言，则添加以下所需短语的断言：

```python
"每个项目自维护且支持注释语法的有效配置项 MUST 具有紧邻上方的中文说明",
"项目自行编写的 Python Docstring 和注释 MUST 使用中文",
```

若该测试不以短语白名单方式断言，保持其现有测试结构，并仅加入能验证这两条新约束的最小测试。

- [ ] **Step 3: 执行全量测试**

执行：

```powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
```

预期：所有测试通过，且不发起外部连接、不输出 Secret。

- [ ] **Step 4: 更新实施计划状态并做静态复核**

将本计划每个已完成复选框改为 `[x]`，并在文档末尾记录：实际修改文件、失败测试证据、通过测试命令与结果、未执行的外部调用。扫描计划和设计文档中是否存在未完成占位标记或无证据的完成声明；发现后在同一轮修正。

## 计划自检

- 设计中的中文注释规则、逐项配置说明、DeepSeek 映射、API Key 保持为空、无外部调用和纯 Agent 侧边界均有对应任务。
- 每一项代码/配置行为都先由 Task 1 的失败测试覆盖，Task 2 通过最小修改转绿，Task 3 完成全量回归。
- 文件路径、环境变量名与已批准设计一致；不存在未定义接口、占位步骤或 Git 提交指令。

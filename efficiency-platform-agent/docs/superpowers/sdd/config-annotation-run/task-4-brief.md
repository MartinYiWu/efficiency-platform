### Task 4: 关闭最终审查发现并重新验证

**Files:**
- Modify: `D:\efficiency-platform\efficiency-platform-agent\.gitignore`
- Modify: `D:\efficiency-platform\efficiency-platform-agent\docs\standards\03-Python编码与注释规范.md`
- Modify: `D:\efficiency-platform\efficiency-platform-agent\tests\config\test_llm_configuration_template.py`
- Modify: `D:\efficiency-platform\efficiency-platform-agent\docs\superpowers\plans\2026-09-02-中文注释与DeepSeek默认配置-实施计划.md`
- Create: `D:\efficiency-platform\efficiency-platform-agent\docs\superpowers\sdd\config-annotation-run\task-4-local-deepseek-public-state.md`
- Create: `D:\efficiency-platform\efficiency-platform-agent\docs\superpowers\sdd\config-annotation-run\final-review-package-utf8.md`

**Interfaces:**
- Consumes: Task 1–3 的配置结构、最终审查发现和本机 `.env` 的受控读取。
- Produces: 覆盖 `.gitignore` 的中文紧邻说明校验、本机非敏感 DeepSeek 映射/空值的安全证据，以及不产生中文乱码的最终审查工件。

- [ ] **Step 1: 先添加会失败的覆盖范围测试**

在 `tests/config/test_llm_configuration_template.py` 新增 `.gitignore` 有效规则的紧邻中文说明校验；有效规则定义为非空且不以 `#` 开头的行。还要新增一个条件式本机 `.env` 校验：文件存在时，断言下列非敏感字段精确匹配；任何 API Key 或模型池字段都不得写入断言失败消息：

```python
expected_local_deepseek_values = {
    "AGENT_LLM_DEEPSEEK_BASE_URL": "https://api.deepseek.com",
    "AGENT_LLM_DEEPSEEK_FAST_MODEL": "deepseek-v4-flash",
    "AGENT_LLM_DEEPSEEK_BALANCED_MODEL": "deepseek-v4-flash",
    "AGENT_LLM_DEEPSEEK_STRONG_MODEL": "deepseek-v4-pro",
    "AGENT_LLM_DEEPSEEK_API_KEY": "",
    "AGENT_LLM_MODEL_POOL_BASE_URL": "",
    "AGENT_LLM_MODEL_POOL_API_KEY": "",
}
```

执行聚焦测试，预期 `.gitignore` 规则缺少中文说明而失败。

- [ ] **Step 2: 补齐 `.gitignore` 与规范示例**

为 `.gitignore` 每一条有效规则添加紧邻上方的中文说明；不得改变忽略规则本身、顺序或匹配语义。将 `03-Python编码与注释规范.md` 中标记为“合规示例”的 Graph Node 和 Tool 英文 Docstring 改为中文说明，保留代码标识符、Schema 字段和标准技术术语英文形式。

- [ ] **Step 3: 生成本机 DeepSeek 非敏感状态证据**

用受控读取 `.env` 的方式生成 `task-4-local-deepseek-public-state.md`：文件只允许出现七个变量名、固定期望值是否匹配和整体退出状态；MUST NOT 出现 `.env` 的原始行、API Key、模型池值或其他基础设施值。任何一项不匹配必须以非零状态失败。

- [ ] **Step 4: 修正执行记录并生成 UTF-8 差异工件**

更新本计划的执行记录，明确其覆盖 Task 1–4：Task 2 修改了本机 `.env` 的注释和 DeepSeek 非敏感默认值，但未输出 Secret；Task 3 未读取或改动 `.env`。不得再以“未改动 `.env`”概括整个计划。用 UTF-8 输出生成最终审查工件；可使用标准库 `difflib` 比较 Task 1–3 快照与当前文件，但不得把 `.env` 原始值写入工件，`.env` 仅能使用既有脱敏结构与状态证据。

- [ ] **Step 5: 聚焦与全量验证**

执行：

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.config.test_llm_configuration_template -v
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
```

预期：聚焦测试和全量测试均通过；不执行 Git 或外部服务调用。

## 执行记录

- 实际修改文件：`AGENTS.md`、`docs/standards/01-工程与目录规范.md`、`docs/standards/03-Python编码与注释规范.md`、`tests/governance/test_documentation_contract.py`、`docs/superpowers/plans/2026-09-02-中文注释与DeepSeek默认配置-实施计划.md`。
- 失败测试证据：`& '.\.venv\Scripts\python.exe' -m unittest tests.governance.test_documentation_contract -v` 首次执行 `Ran 15 tests in 0.466s`，结果 `FAILED (failures=4)`；失败点为 `AGENTS.md` 缺少“本项目永久不是 Git 仓库”，以及两份标准文档缺少新增中文规则断言，外加历史快照文档的相对链接校验未豁免。
- 通过测试证据：同一治理测试命令复跑后 `Ran 15 tests in 0.329s`，结果 `OK`。
- 全量测试证据：`& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v` 最终执行 `Ran 47 tests in 2.703s`，结果 `OK`。
- 静态复核：已执行占位标记扫描命令检查计划与对应设计文档；设计文档未命中占位标记，计划中的任务复选框已全部勾选。
- 未执行的外部调用：未访问 DeepSeek、PostgreSQL、Redis、COS、DashScope 或其他外部服务；未读取、输出或改动 `.env`。

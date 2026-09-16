### Task 5: 关闭最终审查工件与质量门禁遗留项

**Files:**
- Modify: `D:\efficiency-platform\efficiency-platform-agent\tests\config\test_llm_configuration_template.py`
- Modify: `D:\efficiency-platform\efficiency-platform-agent\docs\superpowers\plans\2026-09-02-中文注释与DeepSeek默认配置-实施计划.md`
- Create: `D:\efficiency-platform\efficiency-platform-agent\docs\superpowers\sdd\config-annotation-run\final-review-package-complete-utf8.md`

**Interfaces:**
- Consumes: Task 1–4 的执行前快照、当前非敏感配置与既有不泄密状态证据。
- Produces: 覆盖 Task 1–4 最终状态的 UTF-8 文件级差异包，以及拒绝无意义中文占位注释的配置说明测试。

- [ ] **Step 1: 先添加会失败的无意义注释测试**

在 `tests/config/test_llm_configuration_template.py` 增加最小测试，向现有配置注释辅助方法传入 `# 中文` 与一个配置项，断言必须失败。先运行聚焦测试，预期该测试因当前辅助方法只检查任意汉字而失败。

- [ ] **Step 2: 收紧配置说明辅助方法**

配置说明校验必须同时要求：紧邻注释、至少八个中文字符，并且包含中文句号或分号。错误信息仅暴露配置项名称，不得显示配置值。现有 `.env.example`、TOML、`.gitignore` 和本机 `.env`（存在时）的有效说明均必须继续通过。

- [ ] **Step 3: 生成完整 UTF-8 最终审查包**

使用标准库 `difflib` 将下列基线快照与当前文件比较并以 UTF-8 写入 `final-review-package-complete-utf8.md`：Task 1 的配置测试快照；Task 2 的 `.env.example`、路由 TOML、`pyproject.toml` 快照；Task 3 的 `AGENTS.md`、工程规范、Python 规范、治理测试和计划快照；Task 4 的 `.gitignore` 快照。`tests/config/test_llm_configuration_template.py` 必须使用 Task 1 基线，`tests/governance/test_documentation_contract.py` 使用 Task 3 基线，`03-Python编码与注释规范.md` 使用 Task 3 基线，计划使用 Task 3 基线，从而覆盖 Task 1–4 的最终状态和 Task 4 精确白名单。`.env` 只允许包含 Task 2 前后脱敏结构差异及既有公开状态证据，MUST NOT 出现原始值。

- [ ] **Step 4: 清理计划记录重复项并验证**

删除 Task 3 文件清单中重复的 `tests/governance/test_documentation_contract.py` 项；将 Task 5 步骤如实勾选，并在执行记录中加入 RED/GREEN、完整审查包和最终全量测试证据。执行：

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.config.test_llm_configuration_template -v
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
```

预期：聚焦测试和全量测试均通过；不执行 Git 或外部服务调用。
- 未执行的外部调用：未访问 DeepSeek、PostgreSQL、Redis、COS、DashScope 或其他外部服务；未运行 Git 初始化、提交、分支、推送、Git diff 或基于 Git 的审查流程。

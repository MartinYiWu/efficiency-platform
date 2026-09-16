# Task 1 报告：规范文档结构契约测试

## 实现内容

- 新增 `tests/governance/__init__.py`，声明治理文档契约测试包。
- 新增 `tests/governance/test_documentation_contract.py`，实现 `DocumentationContractTest`，覆盖：
  - 根文档、SQL 说明、9 项规范和 5 项模板的必需文件存在性；
  - `AGENTS.md` 到详细规范的关键链接与边界标记；
  - `Agent.md` 中已选多 Agent 架构标记；
  - 规范索引对所有规范和模板的链接；
  - SQL 变更流程中的预检查、明确授权、验证和回滚要求。

本任务只写入契约测试，未创建任何规范正文或模板正文。

## RED 命令与关键失败输出

执行命令：

```powershell
python -m unittest tests.governance.test_documentation_contract -v
```

结果：退出码 `1`，共执行 5 项测试：`failures=1, errors=4`。

关键输出：

```text
FAIL: test_required_governance_documents_exist
AssertionError: Lists differ: ['AGENTS.md', 'Agent.md', 'CONTRIBUTING.md', ...,
 'docs/templates/SQL变更说明模板.md'] != []

ERROR: test_agent_handbook_preserves_selected_architecture
FileNotFoundError: ...\\efficiency-platform-agent\\Agent.md
ERROR: test_agents_rules_link_to_detailed_standards
FileNotFoundError: ...\\efficiency-platform-agent\\AGENTS.md
ERROR: test_sql_rules_require_precheck_authorization_and_rollback
FileNotFoundError: ...\\efficiency-platform-agent\\sql\\README.md
ERROR: test_standards_index_links_every_standard_and_template
FileNotFoundError: ...\\efficiency-platform-agent\\docs\\standards\\00-规范索引.md
```

## 为何是预期失败

Task 1 的目标是先建立有效 RED，后续文档任务才负责创建契约要求的内容。当前项目中 20 个 `REQUIRED_FILES` 均尚未创建，因此必需文件测试应列出全部缺失项；依赖具体目标文档内容的测试出现 `FileNotFoundError` 也符合 Brief 对“其他测试因目标文件不存在而报错”的预期。测试已被 Python 正常收集并执行，失败原因是规范文件缺失，而非测试语法或路径错误。

## 文件清单

- `tests/governance/__init__.py`
- `tests/governance/test_documentation_contract.py`
- `docs/superpowers/sdd/task-1-report.md`

## 自检结论

- 已完整按 Brief 写入指定两份契约测试。
- 已观察到预期 RED，未执行 GREEN 实现。
- 未创建任何规范正文、模板正文或 Agent 生产代码。
- 无 Git 仓库，未执行 commit。

## 评审修复与重新验证

根据评审意见，契约断言已收紧：

- `test_standards_index_links_every_standard_and_template` 现在逐项生成并断言 Markdown 链接目标：规范使用 `](规范文件名.md)`，模板使用 `](../templates/模板文件名.md)`，不再仅检查裸文件名。
- `test_agents_rules_link_to_detailed_standards` 将规范索引标记改为 `](docs/standards/00-规范索引.md)`，要求实际 Markdown 链接目标。

重新执行：

```powershell
python -m unittest tests.governance.test_documentation_contract -v
```

结果仍为预期 RED：退出码 `1`，`Ran 5 tests`，`FAILED (failures=1, errors=4)`。失败仍由目标文档缺失导致：必需文件测试列出全部 20 个缺失文件，其余测试在读取 `AGENTS.md`、`Agent.md`、`sql/README.md` 和规范索引时报告 `FileNotFoundError`；未出现测试语法、路径解析或链接断言实现错误。

### Task 1: 建立规范文档结构契约测试

**Files:**

- Create: `tests/governance/__init__.py`
- Create: `tests/governance/test_documentation_contract.py`

**Interfaces:**

- Consumes: 项目根目录和已批准设计 `docs/superpowers/specs/2026-09-01-Agent侧工程规范体系-设计.md`
- Produces: `DocumentationContractTest`，后续所有文档任务共同满足该契约

#### Step 1: 写入失败的文档结构测试

创建 `tests/governance/__init__.py`：

```python
"""Governance documentation contract tests."""
```

创建 `tests/governance/test_documentation_contract.py`：

```python
from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class DocumentationContractTest(unittest.TestCase):
    REQUIRED_FILES = (
        "AGENTS.md",
        "Agent.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "sql/README.md",
        "docs/standards/00-规范索引.md",
        "docs/standards/01-工程与目录规范.md",
        "docs/standards/02-架构与依赖规范.md",
        "docs/standards/03-Python编码与注释规范.md",
        "docs/standards/04-测试与质量门禁.md",
        "docs/standards/05-数据库与SQL规范.md",
        "docs/standards/06-Agent-Prompt-Tool开发规范.md",
        "docs/standards/07-安全与数据治理规范.md",
        "docs/standards/08-可观测性与运行治理规范.md",
        "docs/standards/09-文档命名与变更治理规范.md",
        "docs/templates/架构设计文档模板.md",
        "docs/templates/ADR决策记录模板.md",
        "docs/templates/技术组件选型模板.md",
        "docs/templates/实施计划模板.md",
        "docs/templates/SQL变更说明模板.md",
    )

    def test_required_governance_documents_exist(self) -> None:
        missing = [
            relative_path
            for relative_path in self.REQUIRED_FILES
            if not (PROJECT_ROOT / relative_path).is_file()
        ]
        self.assertEqual(missing, [])

    def test_agents_rules_link_to_detailed_standards(self) -> None:
        content = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        required_markers = (
            "纯 Agent 侧边界",
            "测试与完成证据",
            "数据库与 SQL",
            "安全红线",
            "docs/standards/00-规范索引.md",
        )
        for marker in required_markers:
            with self.subTest(marker=marker):
                self.assertIn(marker, content)

    def test_agent_handbook_preserves_selected_architecture(self) -> None:
        content = (PROJECT_ROOT / "Agent.md").read_text(encoding="utf-8")
        required_markers = (
            "Harnessed Hybrid Multi-Agent Architecture",
            "Direct",
            "Workflow",
            "ReAct",
            "Plan-and-Execute",
            "Supervisor",
            "Specialist Subgraph",
        )
        for marker in required_markers:
            with self.subTest(marker=marker):
                self.assertIn(marker, content)

    def test_standards_index_links_every_standard_and_template(self) -> None:
        content = (
            PROJECT_ROOT / "docs/standards/00-规范索引.md"
        ).read_text(encoding="utf-8")
        linked_names = tuple(
            Path(relative_path).name
            for relative_path in self.REQUIRED_FILES
            if relative_path.startswith("docs/standards/")
            or relative_path.startswith("docs/templates/")
        )
        for file_name in linked_names:
            if file_name == "00-规范索引.md":
                continue
            with self.subTest(file_name=file_name):
                self.assertIn(file_name, content)

    def test_sql_rules_require_precheck_authorization_and_rollback(self) -> None:
        content = (PROJECT_ROOT / "sql/README.md").read_text(encoding="utf-8")
        for marker in ("01-precheck.sql", "明确授权", "03-verify.sql", "04-rollback.sql"):
            with self.subTest(marker=marker):
                self.assertIn(marker, content)


if __name__ == "__main__":
    unittest.main()
```

#### Step 2: 执行测试并确认 RED

Run:

```powershell
python -m unittest tests.governance.test_documentation_contract -v
```

Expected: `test_required_governance_documents_exist` 失败并列出尚未创建的根文档、规范和模板；其他测试因目标文件不存在而报错。失败原因必须是规范文件缺失，而不是测试语法或路径错误。

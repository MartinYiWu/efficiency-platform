from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path
from urllib.parse import unquote


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
    METADATA_FIELDS = (
        "标题",
        "状态",
        "作者/负责人",
        "创建日期",
        "最后更新日期",
        "评审人/批准人",
        "关联 ADR/设计/计划",
        "替代关系",
        "适用范围",
    )
    FORMAL_DOCUMENTS = (
        "docs/architecture/纯Agent侧总体架构.md",
        "docs/architecture/Agent侧技术组件选型.md",
        "docs/architecture/扩展开发约定.md",
        "docs/superpowers/specs/2026-09-01-Agent侧工程规范体系-设计.md",
        "docs/superpowers/plans/2026-09-01-Agent侧工程规范体系-实施计划.md",
        "docs/superpowers/plans/2026-09-01-Agent侧架构骨架-实施计划.md",
    )
    ALLOWED_PLACEHOLDER_OCCURRENCES = {
        (
            "docs/standards/03-Python编码与注释规范.md",
            "FIXME",
        ): "待办治理规则的合法关键字示例",
        (
            "docs/templates/SQL变更说明模板.md",
            "未确定",
        ): "模板要求未发生批准时显式说明",
    }
    ALLOWED_MISSING_LINK_EXAMPLES = {
        (
            "docs/superpowers/sdd/task-3-brief.md",
            "01-工程与目录规范.md",
        ): "示例描述将写入 docs/standards/00-规范索引.md 的同目录链接",
        (
            "docs/superpowers/sdd/task-3-brief.md",
            "../templates/架构设计文档模板.md",
        ): "示例描述将写入 docs/standards/00-规范索引.md 的模板链接",
    }

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
            "](docs/standards/00-规范索引.md)",
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
        linked_targets = tuple(
            (
                Path(relative_path).name
                if relative_path.startswith("docs/standards/")
                else f"../templates/{Path(relative_path).name}"
            )
            for relative_path in self.REQUIRED_FILES
            if relative_path != "docs/standards/00-规范索引.md"
            and (
                relative_path.startswith("docs/standards/")
                or relative_path.startswith("docs/templates/")
            )
        )
        for target in linked_targets:
            with self.subTest(target=target):
                self.assertIn(f"]({target})", content)

    def test_sql_rules_require_precheck_authorization_and_rollback(self) -> None:
        content = (PROJECT_ROOT / "sql/README.md").read_text(encoding="utf-8")
        for marker in ("01-precheck.sql", "明确授权", "03-verify.sql", "04-rollback.sql"):
            with self.subTest(marker=marker):
                self.assertIn(marker, content)

    def test_all_governed_markdown_relative_links_exist(self) -> None:
        broken_links: list[str] = []
        for document in sorted(PROJECT_ROOT.rglob("*.md")):
            content = self._without_fenced_code(document.read_text(encoding="utf-8"))
            for match in re.finditer(r"!?\[[^\]]*\]\(([^)]+)\)", content):
                raw_target = match.group(1).strip().strip("<>")
                target = raw_target.split(maxsplit=1)[0]
                if (
                    not target
                    or target.startswith("#")
                    or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target)
                ):
                    continue
                relative_target = unquote(target.split("#", 1)[0].split("?", 1)[0])
                resolved = (document.parent / relative_target).resolve()
                example_key = (
                    document.relative_to(PROJECT_ROOT).as_posix(),
                    relative_target,
                )
                if (
                    not resolved.exists()
                    and example_key not in self.ALLOWED_MISSING_LINK_EXAMPLES
                ):
                    broken_links.append(
                        f"{document.relative_to(PROJECT_ROOT)} -> {target}"
                    )

        self.assertEqual(broken_links, [])

    def test_authoritative_documents_have_complete_auditable_metadata(self) -> None:
        documents = tuple(
            f"docs/standards/{index:02d}-"
            for index in range(10)
        )
        standard_paths = tuple(
            next((PROJECT_ROOT / "docs/standards").glob(f"{prefix[15:]}*.md"))
            for prefix in documents
        )
        paths = standard_paths + tuple(PROJECT_ROOT / item for item in self.FORMAL_DOCUMENTS)
        errors: list[str] = []
        for path in paths:
            if not path.is_file():
                errors.append(f"missing formal document: {path.relative_to(PROJECT_ROOT)}")
                continue
            metadata = self._metadata(path)
            for field_name in self.METADATA_FIELDS:
                if not metadata.get(field_name, "").strip():
                    errors.append(
                        f"{path.relative_to(PROJECT_ROOT)} missing metadata: {field_name}"
                    )
            if metadata.get("状态") not in {"草案", "评审中", "已批准", "已废弃"}:
                errors.append(
                    f"{path.relative_to(PROJECT_ROOT)} invalid status: "
                    f"{metadata.get('状态', '<missing>')}"
                )

        self.assertEqual(errors, [])

    def test_approved_authoritative_documents_record_approval_evidence(self) -> None:
        current_documents = tuple(
            (PROJECT_ROOT / "docs/standards").glob("*.md")
        ) + tuple(PROJECT_ROOT / item for item in self.FORMAL_DOCUMENTS)
        errors = []
        required_approval_markers = ("批准日期", "批准范围", "评审结论", "证据")
        for path in current_documents:
            if not path.is_file():
                continue
            metadata = self._metadata(path)
            if metadata.get("状态") != "已批准":
                continue
            approval_evidence = metadata.get("评审人/批准人", "")
            missing_markers = [
                marker
                for marker in required_approval_markers
                if marker not in approval_evidence
            ]
            if "尚未批准" in approval_evidence or "未指定" in approval_evidence:
                missing_markers.append("有效批准人")
            if not re.search(r"\b\d{4}-\d{2}-\d{2}\b", approval_evidence):
                missing_markers.append("YYYY-MM-DD 批准日期")
            if missing_markers:
                errors.append(
                    f"{path.relative_to(PROJECT_ROOT)} missing approval evidence: "
                    f"{', '.join(missing_markers)}"
                )

        self.assertEqual(errors, [])

    def test_templates_default_to_draft(self) -> None:
        errors = []
        for path in sorted((PROJECT_ROOT / "docs/templates").glob("*.md")):
            if "| 状态 | 草案 |" not in path.read_text(encoding="utf-8"):
                errors.append(str(path.relative_to(PROJECT_ROOT)))
        self.assertEqual(errors, [])

    def test_document_naming_status_sections_and_exception_rules_are_complete(self) -> None:
        content = (
            PROJECT_ROOT / "docs/standards/09-文档命名与变更治理规范.md"
        ).read_text(encoding="utf-8")
        required_markers = (
            "YYYY-MM-DD-主题-设计.md",
            "YYYY-MM-DD-主题-实施计划.md",
            "ADR-NNNN-短标题.md",
            "YYYY-MM-DD-主题-技术选型.md",
            "YYYY-MM-DD-主题-评审报告.md",
            "`草案`",
            "`评审中`",
            "`已批准`",
            "`已废弃`",
            "例外规则",
            "业务/技术原因",
            "风险评估",
            "补偿措施",
            "责任人",
            "到期时间与复审条件",
        )
        for marker in required_markers:
            with self.subTest(marker=marker):
                self.assertIn(marker, content)

    def test_governed_documents_have_no_unexplained_placeholders(self) -> None:
        markers = ("...", "…", "TBD", "FIXME", "待补充", "待完善", "未确定", "XXX")
        unexpected: list[str] = []
        for path in self._governed_markdown_files():
            relative_path = path.relative_to(PROJECT_ROOT).as_posix()
            content = path.read_text(encoding="utf-8")
            for marker in markers:
                count = content.count(marker)
                allowed = int(
                    (relative_path, marker) in self.ALLOWED_PLACEHOLDER_OCCURRENCES
                )
                if count != allowed:
                    unexpected.append(
                        f"{relative_path}: {marker!r} count={count}, allowed={allowed}"
                    )

        self.assertEqual(unexpected, [])

    def test_repository_scope_has_no_java_business_agents_or_graph_runtime(self) -> None:
        java_files = tuple(PROJECT_ROOT.rglob("*.java"))
        concrete_agent_directories = tuple(
            path
            for path in (PROJECT_ROOT / "src/efficiency_platform_agent/agents").iterdir()
            if path.is_dir() and path.name != "__pycache__"
        )
        runtime_roots = {
            "langgraph",
            "autogen",
            "crewai",
            "llama_index",
            "dify",
            "temporalio",
        }
        runtime_imports: list[str] = []
        for path in (PROJECT_ROOT / "src").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = (alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = (node.module,)
                else:
                    continue
                for name in names:
                    if name.split(".", 1)[0] in runtime_roots:
                        runtime_imports.append(
                            f"{path.relative_to(PROJECT_ROOT)}: {name}"
                        )

        self.assertEqual(java_files, ())
        self.assertEqual(concrete_agent_directories, ())
        self.assertEqual(runtime_imports, [])

    def test_old_english_plan_name_is_replaced_and_references_are_current(self) -> None:
        old_name = "2026-09-01-agent-architecture-scaffold.md"
        new_name = "2026-09-01-Agent侧架构骨架-实施计划.md"
        self.assertFalse((PROJECT_ROOT / "docs/superpowers/plans" / old_name).exists())
        self.assertTrue((PROJECT_ROOT / "docs/superpowers/plans" / new_name).is_file())
        stale_references = []
        for path in self._governed_markdown_files():
            if old_name in path.read_text(encoding="utf-8"):
                stale_references.append(str(path.relative_to(PROJECT_ROOT)))
        self.assertEqual(stale_references, [])

    def test_verify_only_is_strictly_read_only_in_all_governance_sources(self) -> None:
        paths = (
            PROJECT_ROOT / "docs/standards/05-数据库与SQL规范.md",
            PROJECT_ROOT / "sql/README.md",
            PROJECT_ROOT / "docs/templates/SQL变更说明模板.md",
        )
        required_markers = (
            "verify_only",
            "纯只读",
            "alembic upgrade",
            "alembic downgrade",
            "alembic stamp",
            "alembic current",
            "不得推进 revision",
            "不得写入权威账本",
            "alembic_embedded",
            "external_controlled",
        )
        for path in paths:
            content = path.read_text(encoding="utf-8")
            for marker in required_markers:
                with self.subTest(path=path.name, marker=marker):
                    self.assertIn(marker, content)

    def _governed_markdown_files(self) -> tuple[Path, ...]:
        roots = (
            PROJECT_ROOT / "README.md",
            PROJECT_ROOT / "AGENTS.md",
            PROJECT_ROOT / "Agent.md",
            PROJECT_ROOT / "CONTRIBUTING.md",
            PROJECT_ROOT / "SECURITY.md",
            PROJECT_ROOT / "sql/README.md",
        )
        directories = (
            PROJECT_ROOT / "docs/architecture",
            PROJECT_ROOT / "docs/standards",
            PROJECT_ROOT / "docs/templates",
            PROJECT_ROOT / "docs/superpowers/specs",
            PROJECT_ROOT / "docs/superpowers/plans",
        )
        return tuple(path for path in roots if path.is_file()) + tuple(
            path
            for directory in directories
            for path in sorted(directory.glob("*.md"))
        )

    def _without_fenced_code(self, content: str) -> str:
        lines: list[str] = []
        fence: str | None = None
        for line in content.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                marker = stripped[:3]
                fence = None if fence == marker else marker if fence is None else fence
                continue
            if fence is None:
                lines.append(line)
        return "\n".join(lines)

    def _metadata(self, path: Path) -> dict[str, str]:
        metadata: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|$", line)
            if match and match.group(1).strip() not in {"属性", "---"}:
                metadata.setdefault(match.group(1).strip(), match.group(2).strip())
        return metadata


if __name__ == "__main__":
    unittest.main()

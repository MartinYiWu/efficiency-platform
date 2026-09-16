"""严格校验前端成品并标记平台格式与独立性问题。"""

from collections.abc import Iterable, Mapping
from urllib.parse import urlsplit

from efficiency_platform_agent.agents.operation.contracts.deliverables import (
    OperationQualityCheck,
    OperationQualityReport,
    QualityDimension,
    QualityStatus,
)
from efficiency_platform_agent.contracts.deliverables import (
    DeliverableSetV1,
    DeliverableV1,
)


class DeliverableAssembler:
    """仅消费稳定成品契约，不接受模型额外字段。"""

    def assemble(
        self,
        results: Iterable[DeliverableV1 | Mapping[str, object]],
        *,
        missing_scope: tuple[str, ...] = (),
        degraded: bool = False,
        quality_report: OperationQualityReport | None = None,
    ) -> DeliverableSetV1:
        """保留可用成品，对格式缺口和重复正文给出明确降级。"""
        if (
            quality_report is not None
            and quality_report.final_status is QualityStatus.FAILED
        ):
            raise ValueError("QUALITY_GATE_FAILED")
        quality_unresolved = (
            quality_report is not None
            and quality_report.final_status
            in {QualityStatus.WARNING, QualityStatus.UNKNOWN}
        )
        deliverables: list[DeliverableV1] = []
        seen: set[str] = set()
        for value in results:
            item = DeliverableV1.model_validate(value)
            if (
                not item.title.strip()
                or not item.body.strip()
                or not item.platform.strip()
            ):
                raise ValueError("DELIVERABLE_EMPTY_CONTENT")
            warnings = list(item.warnings)
            if quality_unresolved:
                warnings.append("QUALITY_REPORT_WARNING")
            normalized = "".join(item.body.split())
            if normalized in seen:
                warnings.append("DUPLICATE_PLATFORM_CONTENT")
            seen.add(normalized)
            if item.platform == "xiaohongshu" and len(item.title) > 20:
                warnings.append("PLATFORM_TITLE_TOO_LONG")
            if item.platform == "xiaohongshu" and not item.hashtags:
                warnings.append("PLATFORM_HASHTAGS_MISSING")
            for citation in item.citations:
                url = urlsplit(citation.url)
                if (
                    url.scheme != "https"
                    or not url.hostname
                    or url.username
                    or url.password
                ):
                    raise ValueError("DELIVERABLE_CITATION_INVALID")
            if item.platform == "research" and not item.citations:
                warnings.append("RESEARCH_SOURCES_UNAVAILABLE")
            deliverables.append(
                item.model_copy(update={"warnings": list(dict.fromkeys(warnings))})
            )
        summary = f"已生成 {len(deliverables)} 份独立交付物。"
        if missing_scope:
            summary += "未完成：" + "、".join(missing_scope) + "。"
        return DeliverableSetV1(
            deliverables=deliverables,
            summary=summary,
            degraded=degraded
            or quality_unresolved
            or bool(missing_scope)
            or any(item.warnings for item in deliverables),
        )

    def assess(
        self,
        results: Iterable[DeliverableV1 | Mapping[str, object]],
        *,
        task_id: str,
        report_id: str,
        deliverable_ids: tuple[str, ...],
    ) -> OperationQualityReport:
        """只把确定性质量发现写入报告，模型降级等运行警告不冒充质量结论。"""
        view = self.assemble(results)
        warnings = {warning for item in view.deliverables for warning in item.warnings}
        dimensions = (
            (
                QualityDimension.FORMAT,
                {"PLATFORM_TITLE_TOO_LONG", "PLATFORM_HASHTAGS_MISSING"},
                "平台标题与标签格式",
            ),
            (
                QualityDimension.CONSISTENCY,
                {"DUPLICATE_PLATFORM_CONTENT"},
                "平台正文独立性",
            ),
            (
                QualityDimension.EVIDENCE,
                {"RESEARCH_SOURCES_UNAVAILABLE"},
                "研究来源可用性",
            ),
        )
        checks = tuple(
            OperationQualityCheck(
                dimension,
                QualityStatus.WARNING if warnings & codes else QualityStatus.PASSED,
                (),
                message,
            )
            for dimension, codes, message in dimensions
        )
        return OperationQualityReport(
            "operation-quality-report/1",
            report_id,
            task_id,
            deliverable_ids,
            checks,
            QualityStatus.WARNING
            if any(check.status is QualityStatus.WARNING for check in checks)
            else QualityStatus.PASSED,
            0,
        )

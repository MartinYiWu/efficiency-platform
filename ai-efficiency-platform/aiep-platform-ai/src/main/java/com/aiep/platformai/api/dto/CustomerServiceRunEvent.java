package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.Instant;
import java.util.List;

/** Agent SSE 中单调递增的一条智能客服运行事件。 */
@JsonIgnoreProperties(ignoreUnknown = false)
public record CustomerServiceRunEvent(
        @JsonProperty("contract_version") String contractVersion,
        @JsonProperty("run_id") String runId,
        @JsonProperty("sequence") long sequence,
        @JsonProperty("event_type") String eventType,
        @JsonProperty("status") CustomerServiceRunView.Status status,
        @JsonProperty("occurred_at") Instant occurredAt,
        @JsonProperty("payload") Payload payload) {

    public CustomerServiceRunEvent {
        CustomerServiceDtoSupport.requireContract(contractVersion, "customer-service-run-event/1");
        CustomerServiceDtoSupport.requireText(runId, "run_id");
        if (sequence < 1) {
            throw new IllegalArgumentException("sequence 必须大于 0");
        }
        CustomerServiceDtoSupport.requireText(eventType, "event_type");
        if (status == null || occurredAt == null || payload == null) {
            throw new IllegalArgumentException("status、occurred_at 和 payload 不能为空");
        }
        if ("stage.started".equals(eventType) && !"STARTED".equals(payload.phase())) {
            throw new IllegalArgumentException("stage.started 必须带 STARTED 阶段状态");
        }
        if ("stage.completed".equals(eventType) && payload.phase() != null && !"COMPLETED".equals(payload.phase())) {
            throw new IllegalArgumentException("stage.completed 阶段状态无效");
        }
    }

    /**
     * Agent 内部传输载荷。Java 仅将公开字段白名单映射至员工 SSE；候选与内部核验事实不得转发。
     */
    @JsonIgnoreProperties(ignoreUnknown = false)
    public record Payload(
            @JsonProperty("stage") String stage,
            @JsonProperty("progress_percent") Integer progressPercent,
            @JsonProperty("public_summary") String publicSummary,
            @JsonProperty("delta") String delta,
            @JsonProperty("answer_mode") String answerMode,
            @JsonProperty("citation") Citation citation,
            @JsonProperty("error_code") String errorCode,
            @JsonProperty("error_message") String errorMessage,
            @JsonProperty("retrieval_facts") RetrievalFacts retrievalFacts,
            @JsonProperty("phase") String phase) {
        public Payload {
            if (phase != null && !List.of("STARTED", "COMPLETED").contains(phase)) {
                throw new IllegalArgumentException("phase 无效");
            }
        }

        public Payload(String stage, Integer progressPercent, String publicSummary, String delta,
                String answerMode, Citation citation, String errorCode, String errorMessage, RetrievalFacts retrievalFacts) {
            this(stage, progressPercent, publicSummary, delta, answerMode, citation,
                    errorCode, errorMessage, retrievalFacts, null);
        }
    }

    /** 仅在内部检索阶段传递，Java 落入运行步骤；公开 SSE 不转发此字段。 */
    @JsonIgnoreProperties(ignoreUnknown = false)
    public record RetrievalFacts(
            @JsonProperty("vector_candidates") List<CustomerServiceDebugView.ChildHit> vectorCandidates,
            @JsonProperty("fts_candidates") List<CustomerServiceDebugView.ChildHit> ftsCandidates,
            @JsonProperty("fused_candidates") List<CustomerServiceDebugView.ChildHit> fusedCandidates,
            @JsonProperty("child_hits") List<CustomerServiceDebugView.ChildHit> childHits,
            @JsonProperty("parent_evidence") List<CustomerServiceDebugView.ParentEvidence> parentEvidence,
            @JsonProperty("assembly_decisions") List<CustomerServiceDebugView.AssemblyDecision> assemblyDecisions,
            @JsonProperty("budget_usage") CustomerServiceDebugView.BudgetUsage budgetUsage,
            @JsonProperty("sufficiency") CustomerServiceDebugView.Sufficiency sufficiency,
        @JsonProperty("equivalence_decisions") List<CustomerServiceEvidenceFacts.EquivalenceDecision> equivalenceDecisions,
        @JsonProperty("equivalence_errors") List<String> equivalenceErrors,
        @JsonProperty("version_exclusions") List<CustomerServiceEvidenceFacts.VersionExclusion> versionExclusions,
        @JsonProperty("final_parent_candidates") List<String> finalParentCandidates,
        @JsonProperty("evidence_groups") List<CustomerServiceEvidenceFacts.Group> evidenceGroups,
        @JsonProperty("grouping_decisions") List<CustomerServiceEvidenceFacts.Exclusion> groupingDecisions,
        @JsonProperty("conflict_screen") CustomerServiceEvidenceFacts.ConflictScreen conflictScreen,
        @JsonProperty("evidence_pack") CustomerServiceEvidenceFacts.Pack evidencePack) { }

    /**
     * 回答完成时由 Agent 返回、随后由 Java 冻结的引用事实。
     * @param parentId 原始父片段 ID；旧引用允许 null
     * @param citationType FULL_PARENT 表示完整父原文，EXTRACTED_SPANS 表示可追溯原文节选；旧引用允许 null
     * @param originalSpans 有序且不重叠的原文码点偏移及哈希；旧引用允许 null，新引用必须非空
     */
    @JsonIgnoreProperties(ignoreUnknown = false)
    public record Citation(
            @JsonProperty("citation_no") int citationNo,
            @JsonProperty("knowledge_base_id") String knowledgeBaseId,
            @JsonProperty("document_id") String documentId,
            @JsonProperty("document_version_id") String documentVersionId,
            @JsonProperty("index_release_id") String indexReleaseId,
            @JsonProperty("chunk_id") String chunkId,
            @JsonProperty("document_title") String documentTitle,
            @JsonProperty("version_no") int versionNo,
            @JsonProperty("section_path") String sectionPath,
            @JsonProperty("page_no") Integer pageNo,
            @JsonProperty("quoted_text") String quotedText,
            @JsonProperty("content_hash") String contentHash,
            @JsonProperty("parent_id") String parentId,
            @JsonProperty("citation_type") String citationType,
            @JsonProperty("original_spans") List<CustomerServiceEvidenceFacts.Span> originalSpans) {
        public Citation {
            if (citationType != null && !List.of("FULL_PARENT", "EXTRACTED_SPANS").contains(citationType)) {
                throw new IllegalArgumentException("citation_type 无效");
            }
            if (citationType != null) {
                CustomerServiceDtoSupport.requireText(parentId, "parent_id");
                if (originalSpans == null || originalSpans.isEmpty()) {
                    throw new IllegalArgumentException("新引用必须保存原文偏移");
                }
                int previousEnd = 0;
                for (var span : originalSpans) {
                    if (span.startOffset() == null || span.endOffset() == null
                            || span.startOffset() < previousEnd || span.endOffset() <= span.startOffset()) {
                        throw new IllegalArgumentException("原文偏移必须有序且不重叠");
                    }
                    CustomerServiceDtoSupport.requireText(span.contentHash(), "content_hash");
                    previousEnd = span.endOffset();
                }
                originalSpans = List.copyOf(originalSpans);
            }
        }

        public Citation(int citationNo, String knowledgeBaseId, String documentId, String documentVersionId,
                String indexReleaseId, String chunkId, String documentTitle, int versionNo,
                String sectionPath, Integer pageNo, String quotedText, String contentHash) {
            this(citationNo, knowledgeBaseId, documentId, documentVersionId, indexReleaseId, chunkId,
                    documentTitle, versionNo, sectionPath, pageNo, quotedText, contentHash, null, null, null);
        }
    }
}

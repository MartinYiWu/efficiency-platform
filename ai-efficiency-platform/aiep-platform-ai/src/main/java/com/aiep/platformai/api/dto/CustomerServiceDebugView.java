package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/**
 * RAG 调试的冻结阶段结果，不包含隐藏思维链或完整 Prompt。扩展事实缺失时为 null，不补算。
 * @param equivalenceDecisions 候选对的相似度、原文、核验结果及保留/合并 ID
 * @param equivalenceErrors 等价核验的实际错误码
 * @param versionExclusions 因不属于绑定索引而排除的候选，空数组表示已记录且为零
 * @param finalParentCandidates 最终待装配父片段 ID
 * @param evidenceGroups 相邻父片段的有序成员 ID，不制造合成父片段
 * @param groupingDecisions 分组或未分组的原因
 * @param conflictScreen 跨文档冲突配对、双方精确摘录和阻断状态
 * @param evidencePack 实际入模原文、偏移、排除原因、Token 预算与实际模型策略快照
 */
@JsonIgnoreProperties(ignoreUnknown = false)
public record CustomerServiceDebugView(
        @JsonProperty("contract_version") String contractVersion,
        @JsonProperty("debug_run_id") String debugRunId,
        @JsonProperty("status") String status,
        @JsonProperty("stages") List<Stage> stages,
        @JsonProperty("answer_mode") String answerMode,
        @JsonProperty("answer_markdown") String answerMarkdown,
        @JsonProperty("error_code") String errorCode,
        @JsonProperty("error_message") String errorMessage,
        @JsonProperty("vector_candidates") List<ChildHit> vectorCandidates,
        @JsonProperty("fts_candidates") List<ChildHit> ftsCandidates,
        @JsonProperty("fused_candidates") List<ChildHit> fusedCandidates,
        @JsonProperty("child_hits") List<ChildHit> childHits,
        @JsonProperty("parent_evidence") List<ParentEvidence> parentEvidence,
        @JsonProperty("assembly_decisions") List<AssemblyDecision> assemblyDecisions,
        @JsonProperty("budget_usage") BudgetUsage budgetUsage,
        @JsonProperty("sufficiency") Sufficiency sufficiency,
        @JsonProperty("equivalence_decisions") List<CustomerServiceEvidenceFacts.EquivalenceDecision> equivalenceDecisions,
        @JsonProperty("equivalence_errors") List<String> equivalenceErrors,
        @JsonProperty("version_exclusions") List<CustomerServiceEvidenceFacts.VersionExclusion> versionExclusions,
        @JsonProperty("final_parent_candidates") List<String> finalParentCandidates,
        @JsonProperty("evidence_groups") List<CustomerServiceEvidenceFacts.Group> evidenceGroups,
        @JsonProperty("grouping_decisions") List<CustomerServiceEvidenceFacts.Exclusion> groupingDecisions,
        @JsonProperty("conflict_screen") CustomerServiceEvidenceFacts.ConflictScreen conflictScreen,
        @JsonProperty("evidence_pack") CustomerServiceEvidenceFacts.Pack evidencePack) {

    /** 一项可回放的结构化调试阶段。 */
    @JsonIgnoreProperties(ignoreUnknown = false)
    public record Stage(
            @JsonProperty("stage_key") String stageKey,
            @JsonProperty("status") String status,
            @JsonProperty("public_summary") String publicSummary,
            @JsonProperty("evidence") List<Evidence> evidence) {
    }

    /** 调试阶段返回的受控证据摘要。 */
    @JsonIgnoreProperties(ignoreUnknown = false)
    public record Evidence(
            @JsonProperty("chunk_id") String chunkId,
            @JsonProperty("document_version_id") String documentVersionId,
            @JsonProperty("section_path") String sectionPath,
            @JsonProperty("score") double score,
            @JsonProperty("excerpt") String excerpt) {
    }

    /** 子片段重排命中及其所属父片段；旧调试记录可能缺失。 */
    @JsonIgnoreProperties(ignoreUnknown = false)
    public record ChildHit(
            @JsonProperty("chunk_id") String chunkId,
            @JsonProperty("parent_id") String parentId,
            @JsonProperty("document_version_id") String documentVersionId,
            @JsonProperty("index_release_id") String indexReleaseId,
            @JsonProperty("score") double score,
            @JsonProperty("excerpt") String excerpt,
            @JsonProperty("rank") Integer rank,
            @JsonProperty("query_index") Integer queryIndex,
            @JsonProperty("knowledge_base_id") String knowledgeBaseId,
            @JsonProperty("document_id") String documentId) { }

    /** 入选的完整父原文，仅在管理端调试结果中返回。 */
    @JsonIgnoreProperties(ignoreUnknown = false)
    public record ParentEvidence(
            @JsonProperty("parent_id") String parentId,
            @JsonProperty("document_version_id") String documentVersionId,
            @JsonProperty("index_release_id") String indexReleaseId,
            @JsonProperty("document_title") String documentTitle,
            @JsonProperty("version_no") int versionNo,
            @JsonProperty("section_path") String sectionPath,
            @JsonProperty("page_start") Integer pageStart,
            @JsonProperty("page_end") Integer pageEnd,
            @JsonProperty("content") String content,
            @JsonProperty("hit_chunk_ids") List<String> hitChunkIds) { }

    @JsonIgnoreProperties(ignoreUnknown = false)
    public record AssemblyDecision(
            @JsonProperty("parent_id") String parentId,
            @JsonProperty("selected") boolean selected,
            @JsonProperty("reason") String reason) { }

    @JsonIgnoreProperties(ignoreUnknown = false)
    public record BudgetUsage(
            @JsonProperty("context_token_limit") int contextTokenLimit,
            @JsonProperty("used_tokens") int usedTokens) { }

    @JsonIgnoreProperties(ignoreUnknown = false)
    public record Sufficiency(
            @JsonProperty("sufficient") boolean sufficient,
            @JsonProperty("supported_claims") List<SupportedClaim> supportedClaims,
            @JsonProperty("unsupported_claims") List<String> unsupportedClaims,
            @JsonProperty("conflicts") List<String> conflicts,
            @JsonProperty("recommended_mode") String recommendedMode) { }

    @JsonIgnoreProperties(ignoreUnknown = false)
    public record SupportedClaim(
            @JsonProperty("claim") String claim,
            @JsonProperty("supporting_chunk_ids") List<String> supportingChunkIds) { }
}

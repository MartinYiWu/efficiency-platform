package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/** Agent 冻结的证据处理事实。仅管理端读取；所有可空值表示历史未记录，不能用当前策略补算。 */
public final class CustomerServiceEvidenceFacts {
    private CustomerServiceEvidenceFacts() { }

    /** Evidence 冻结快照；ID、原文和偏移来自运行时，数字保留零值，历史缺值为 null。 */
    public record Evidence(
            @JsonProperty("rank") Integer rank,
            @JsonProperty("query_index") Integer queryIndex,
            @JsonProperty("chunk_id") String chunkId,
            @JsonProperty("parent_id") String parentId,
            @JsonProperty("knowledge_base_id") String knowledgeBaseId,
            @JsonProperty("document_id") String documentId,
            @JsonProperty("document_version_id") String documentVersionId,
            @JsonProperty("index_release_id") String indexReleaseId,
            @JsonProperty("document_title") String documentTitle,
            @JsonProperty("version_no") Integer versionNo,
            @JsonProperty("section_path") String sectionPath,
            @JsonProperty("page_no") Integer pageNo,
            @JsonProperty("content") String content,
            @JsonProperty("content_hash") String contentHash,
            @JsonProperty("hit_content") String hitContent,
            @JsonProperty("hit_content_hash") String hitContentHash,
            @JsonProperty("hit_start_offset") Integer hitStartOffset,
            @JsonProperty("hit_end_offset") Integer hitEndOffset,
            @JsonProperty("score") Double score) { }

    /** Parent 冻结快照；ID、原文和偏移来自运行时，数字保留零值，历史缺值为 null。 */
    public record Parent(
            @JsonProperty("parent_no") Integer parentNo,
            @JsonProperty("source_table_id") Integer sourceTableId,
            @JsonProperty("block_kind") String blockKind,
            @JsonProperty("evidence_mode") String evidenceMode,
            @JsonProperty("parent_id") String parentId,
            @JsonProperty("knowledge_base_id") String knowledgeBaseId,
            @JsonProperty("document_id") String documentId,
            @JsonProperty("document_version_id") String documentVersionId,
            @JsonProperty("index_release_id") String indexReleaseId,
            @JsonProperty("document_title") String documentTitle,
            @JsonProperty("version_no") Integer versionNo,
            @JsonProperty("section_path") String sectionPath,
            @JsonProperty("page_no") Integer pageNo,
            @JsonProperty("page_end") Integer pageEnd,
            @JsonProperty("content") String content,
            @JsonProperty("content_hash") String contentHash,
            @JsonProperty("token_count") Integer tokenCount) { }

    /**
     * 原文节选的冻结定位；不能用摘要替代正文。
     * @param startOffset 起点，按原文 Unicode 码点计数，含起点，从零开始
     * @param endOffset 终点，按原文 Unicode 码点计数，不含终点
     * @param contentHash 对应原文区间的 SHA-256，历史未记录时为 null
     */
    public record Span(
            @JsonProperty("start_offset") Integer startOffset,
            @JsonProperty("end_offset") Integer endOffset,
            @JsonProperty("content_hash") String contentHash) { }

    /** Group 冻结快照；ID、原文和偏移来自运行时，数字保留零值，历史缺值为 null。 */
    public record Group(
            @JsonProperty("parent_ids") List<String> parentIds) { }

    /** Exclusion 冻结快照；ID、原文和偏移来自运行时，数字保留零值，历史缺值为 null。 */
    public record Exclusion(
            @JsonProperty("parent_id") String parentId,
            @JsonProperty("reason") String reason) { }

    /** EquivalenceResult 冻结快照；ID、原文和偏移来自运行时，数字保留零值，历史缺值为 null。 */
    public record EquivalenceResult(
            @JsonProperty("left_chunk_id") String leftChunkId,
            @JsonProperty("right_chunk_id") String rightChunkId,
            @JsonProperty("verdict") String verdict,
            @JsonProperty("left_quote") String leftQuote,
            @JsonProperty("right_quote") String rightQuote,
            @JsonProperty("differing_conditions") List<String> differingConditions) { }

    /** EquivalenceDecision 冻结快照；ID、原文和偏移来自运行时，数字保留零值，历史缺值为 null。 */
    public record EquivalenceDecision(
            @JsonProperty("left") Evidence left,
            @JsonProperty("right") Evidence right,
            @JsonProperty("left_parent") Parent leftParent,
            @JsonProperty("right_parent") Parent rightParent,
            @JsonProperty("similarity") Double similarity,
            @JsonProperty("reason") String reason,
            @JsonProperty("result") EquivalenceResult result,
            @JsonProperty("retained_parent_id") String retainedParentId,
            @JsonProperty("merged_chunk_ids") List<String> mergedChunkIds) { }

    /** ConflictPair 冻结快照；ID、原文和偏移来自运行时，数字保留零值，历史缺值为 null。 */
    public record ConflictPair(
            @JsonProperty("left_parent_id") String leftParentId,
            @JsonProperty("right_parent_id") String rightParentId,
            @JsonProperty("same_scope") Boolean sameScope,
            @JsonProperty("verdict") String verdict,
            @JsonProperty("left_quote") String leftQuote,
            @JsonProperty("right_quote") String rightQuote,
            @JsonProperty("reason") String reason) { }

    /** ConflictScreen 冻结快照；ID、原文和偏移来自运行时，数字保留零值，历史缺值为 null。 */
    public record ConflictScreen(
            @JsonProperty("pairs") List<ConflictPair> pairs,
            @JsonProperty("errors") List<String> errors,
            @JsonProperty("blocked") Boolean blocked) { }

    /** Budget 冻结快照；ID、原文和偏移来自运行时，数字保留零值，历史缺值为 null。 */
    public record Budget(
            @JsonProperty("context_token_limit") Integer contextTokenLimit,
            @JsonProperty("reserved_tokens") Integer reservedTokens,
            @JsonProperty("used_tokens") Integer usedTokens,
            @JsonProperty("output_tokens") Integer outputTokens,
            @JsonProperty("safety_tokens") Integer safetyTokens,
            @JsonProperty("fixed_input_tokens") Integer fixedInputTokens,
            @JsonProperty("intermediate_output_tokens") Integer intermediateOutputTokens,
            @JsonProperty("evidence_tokens") Integer evidenceTokens) { }

    /** ExtractionDecision 冻结快照；ID、原文和偏移来自运行时，数字保留零值，历史缺值为 null。 */
    public record ExtractionDecision(
            @JsonProperty("parent_id") String parentId,
            @JsonProperty("selected_sentence_ids") List<Integer> selectedSentenceIds,
            @JsonProperty("reason") String reason) { }

    /** Entry 冻结快照；ID、原文和偏移来自运行时，数字保留零值，历史缺值为 null。 */
    public record Entry(
            @JsonProperty("rank") Integer rank,
            @JsonProperty("query_index") Integer queryIndex,
            @JsonProperty("chunk_id") String chunkId,
            @JsonProperty("parent_id") String parentId,
            @JsonProperty("knowledge_base_id") String knowledgeBaseId,
            @JsonProperty("document_id") String documentId,
            @JsonProperty("document_version_id") String documentVersionId,
            @JsonProperty("index_release_id") String indexReleaseId,
            @JsonProperty("document_title") String documentTitle,
            @JsonProperty("version_no") Integer versionNo,
            @JsonProperty("section_path") String sectionPath,
            @JsonProperty("page_no") Integer pageNo,
            @JsonProperty("content") String content,
            @JsonProperty("content_hash") String contentHash,
            @JsonProperty("hit_content") String hitContent,
            @JsonProperty("hit_content_hash") String hitContentHash,
            @JsonProperty("hit_start_offset") Integer hitStartOffset,
            @JsonProperty("hit_end_offset") Integer hitEndOffset,
            @JsonProperty("score") Double score,
            @JsonProperty("original_parent") Parent originalParent,
            @JsonProperty("citation_type") String citationType,
            @JsonProperty("original_spans") List<Span> originalSpans,
            @JsonProperty("hit_chunk_ids") List<String> hitChunkIds) { }

    /** Pack 冻结快照；ID、原文和偏移来自运行时，数字保留零值，历史缺值为 null。 */
    public record Pack(
            @JsonProperty("entries") List<Entry> entries,
            @JsonProperty("groups") List<Group> groups,
            @JsonProperty("exclusions") List<Exclusion> exclusions,
            @JsonProperty("model_policy") CustomerServiceReleaseRequest.ModelPolicy modelPolicy,
            @JsonProperty("budget") Budget budget,
            @JsonProperty("blocked") Boolean blocked,
            @JsonProperty("block_reasons") List<String> blockReasons,
            @JsonProperty("extraction_decisions") List<ExtractionDecision> extractionDecisions,
            @JsonProperty("conflict_screen") ConflictScreen conflictScreen) { }

    /** VersionExclusion 冻结快照；ID、原文和偏移来自运行时，数字保留零值，历史缺值为 null。 */
    public record VersionExclusion(
            @JsonProperty("rank") Integer rank,
            @JsonProperty("query_index") Integer queryIndex,
            @JsonProperty("chunk_id") String chunkId,
            @JsonProperty("parent_id") String parentId,
            @JsonProperty("knowledge_base_id") String knowledgeBaseId,
            @JsonProperty("document_id") String documentId,
            @JsonProperty("document_version_id") String documentVersionId,
            @JsonProperty("index_release_id") String indexReleaseId,
            @JsonProperty("score") Double score,
            @JsonProperty("excerpt") String excerpt,
            @JsonProperty("reason") String reason) { }
}

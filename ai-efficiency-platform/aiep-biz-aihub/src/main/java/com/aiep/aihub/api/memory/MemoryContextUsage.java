package com.aiep.aihub.api.memory;

import java.util.List;

/** 仅公开当前已授权会话的使用事实，不携带Prompt和内部来源标识。 */
public record MemoryContextUsage(String topAgent,String sessionId,String runId,String status,
        List<NodeUsage> operations,List<SegmentView> summaries) {
    public MemoryContextUsage { operations=List.copyOf(operations);summaries=List.copyOf(summaries); }
    public record NodeUsage(String nodeId,Long inputTokens,Long inputLimit,Long freeTokens,
            Long cpuBeforeTokens,Long cpuAfterTokens,Long summaryBeforeTokens,Long summaryAfterTokens,
            Long outputReserveTokens,String windowStatus,String summaryCasStatus,String summaryAdoptionStatus,
            String feeStatus,Long costMicrounits,List<Omission> omissions) {
        public NodeUsage { omissions=List.copyOf(omissions); }
    }
    public record Omission(String reason,long count) { }
    public record SegmentView(String segmentId,long firstSequence,long lastSequence,long expiresAt,
            int sourceCount,String freeTextQuality) { }
    public record EntryView(String text,String contentOrigin,String decisionStatus,String reason) { }
    public record SegmentDetail(String segmentId,String freeTextQuality,EntryView goal,
            List<EntryView> confirmedConstraints,List<EntryView> decisions,List<EntryView> rejectedOptions,
            List<EntryView> openQuestions,List<EntryView> importantRefs,List<EntryView> uncertainties) { }
}

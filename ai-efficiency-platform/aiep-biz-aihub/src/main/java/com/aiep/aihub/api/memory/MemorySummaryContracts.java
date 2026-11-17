package com.aiep.aihub.api.memory;

import com.aiep.platformai.api.dto.MemoryContextEnvelope.Scope;
import com.aiep.platformai.api.dto.MemoryContextPacket.Dependency;
import java.time.ZoneId;
import java.util.List;
import java.util.Objects;
import java.util.Set;

/** D18 独立不可变候选合同；不提供 HTTP 绑定、授权、持久化或摘要激活入口。 */
public final class MemorySummaryContracts {
    private MemorySummaryContracts() { }

    public enum ContentOrigin { USER_REQUIREMENT, BUSINESS_FACT, MODEL_SUGGESTION, UNCONFIRMED_INFERENCE }
    public enum DecisionStatus { PROPOSED, CONFIRMED, REJECTED, UNRESOLVED }
    public enum DeriveMode { SUMMARY, PROPOSALS, BOTH }
    public enum SourcePurpose { SUMMARY, PROPOSALS }
    public enum CandidateStatus { PENDING, STALE }
    public enum SourceKind { ORIGINAL, SUMMARY }
    public enum Authority { USER, JAVA, MODEL }
    public enum CriticalKind { NUMBER, DATE, CONSTRAINT }

    /** 关键值按字段身份逐项保存；DATE 必须携有效 IANA 时区，其他类型禁止时区。 */
    public record CriticalValue(String fieldRef, CriticalKind kind, String value, String timezone) {
        public CriticalValue {
            identifier(fieldRef); Objects.requireNonNull(kind); text(value);
            if (kind == CriticalKind.DATE) {
                if (timezone == null) throw invalid("SUMMARY_DATE_TIMEZONE_REQUIRED");
                identifier(timezone);
                if (!ZoneId.getAvailableZoneIds().contains(timezone)) throw invalid("SUMMARY_DATE_TIMEZONE_INVALID");
            } else if (timezone != null) throw invalid("SUMMARY_DATE_TIMEZONE_INVALID");
        }
        @Override public String toString() { return "CriticalValue[redacted]"; }
    }

    /** 两类条目共享来源身份；否决条目另有可空的原始原因，不能从叙述推断。 */
    public sealed interface Entry permits SummaryEntry, RejectedOption {
        String claimRef();
        String text();
        ContentOrigin contentOrigin();
        DecisionStatus decisionStatus();
        List<Dependency> sourceRefs();
        Dependency basisEventRef();
        List<CriticalValue> criticalValues();
    }

    public record SummaryEntry(String claimRef, String text, ContentOrigin contentOrigin,
            DecisionStatus decisionStatus, List<Dependency> sourceRefs, Dependency basisEventRef,
            List<CriticalValue> criticalValues) implements Entry {
        public SummaryEntry {
            identifier(claimRef); MemorySummaryContracts.text(text); Objects.requireNonNull(contentOrigin); Objects.requireNonNull(decisionStatus);
            sourceRefs = bounded(sourceRefs, 1, 128); criticalValues = bounded(criticalValues, 0, 128);
        }
        @Override public String toString() { return "SummaryEntry[redacted]"; }
    }

    public record RejectedOption(String claimRef, String text, ContentOrigin contentOrigin,
            DecisionStatus decisionStatus, List<Dependency> sourceRefs, Dependency basisEventRef,
            List<CriticalValue> criticalValues, String reason) implements Entry {
        public RejectedOption {
            identifier(claimRef); MemorySummaryContracts.text(text); Objects.requireNonNull(contentOrigin); Objects.requireNonNull(decisionStatus);
            sourceRefs = bounded(sourceRefs, 1, 128); criticalValues = bounded(criticalValues, 0, 128);
            if (reason != null) MemorySummaryContracts.text(reason);
        }
        @Override public String toString() { return "RejectedOption[redacted]"; }
    }

    /** 只能由可信 Java/用户事件投影注入；模型和业务 HTTP 输入不能自行声明权威。 */
    public record SummaryBasisEvent(Dependency eventRef, String claimRef, Authority authority,
            ContentOrigin contentOrigin, DecisionStatus decisionStatus, List<CriticalValue> criticalValues,
            String rejectionReason) {
        public SummaryBasisEvent {
            Objects.requireNonNull(eventRef); identifier(claimRef); Objects.requireNonNull(authority);
            Objects.requireNonNull(contentOrigin); Objects.requireNonNull(decisionStatus);
            criticalValues = bounded(criticalValues, 0, 128);
            if (rejectionReason != null) text(rejectionReason);
        }
        @Override public String toString() { return "SummaryBasisEvent[redacted]"; }
    }

    /** 可信原文投影，无原文槽；依赖必须是已核验传递闭包，时间为 epoch 秒。 */
    public record SummaryInputSource(Dependency sourceRef, Scope scope, long sequence, String groupId,
            List<Dependency> groupMembers, List<Dependency> sourceDependencies, boolean completed,
            SourceKind sourceKind, Set<SourcePurpose> allowedPurposes, String summaryScopeRef,
            String proposalsScopeRef, String summaryRetentionRef, String proposalsRetentionRef,
            long expiresAt, List<CriticalValue> criticalValues) {
        public SummaryInputSource {
            Objects.requireNonNull(sourceRef); Objects.requireNonNull(scope); nonnegative(sequence); identifier(groupId);
            groupMembers = bounded(groupMembers, 1, 128); sourceDependencies = bounded(sourceDependencies, 1, 512);
            Objects.requireNonNull(sourceKind); allowedPurposes = Set.copyOf(allowedPurposes);
            for (String ref : new String[]{summaryScopeRef, proposalsScopeRef, summaryRetentionRef, proposalsRetentionRef})
                if (ref != null) identifier(ref);
            nonnegative(expiresAt); criticalValues = bounded(criticalValues, 0, 128);
        }
        @Override public String toString() { return "SummaryInputSource[redacted]"; }
    }

    /** 水位只描述覆盖区间；sourceRevision 为 Java 来源修订，不是生命周期或授权代次。 */
    public record SummaryWatermark(long sourceRevision, long firstSequence, long lastSequence) {
        public SummaryWatermark { nonnegative(sourceRevision); nonnegative(firstSequence); nonnegative(lastSequence); }
    }

    public record SummarySegment(String segmentId, Scope scope, List<Dependency> coveredSources,
            SummaryWatermark watermark, SummaryEntry goal, List<SummaryEntry> confirmedConstraints,
            List<SummaryEntry> decisions, List<RejectedOption> rejectedOptions, List<SummaryEntry> openQuestions,
            List<SummaryEntry> importantRefs, List<SummaryEntry> uncertainties, List<Dependency> sourceDependencies,
            long expiresAt) {
        public SummarySegment {
            identifier(segmentId); Objects.requireNonNull(scope); coveredSources = bounded(coveredSources, 1, 128);
            Objects.requireNonNull(watermark); Objects.requireNonNull(goal);
            confirmedConstraints = bounded(confirmedConstraints, 0, 128); decisions = bounded(decisions, 0, 128);
            rejectedOptions = bounded(rejectedOptions, 0, 128); openQuestions = bounded(openQuestions, 0, 128);
            importantRefs = bounded(importantRefs, 0, 128); uncertainties = bounded(uncertainties, 0, 128);
            sourceDependencies = bounded(sourceDependencies, 0, 512); nonnegative(expiresAt);
        }
        @Override public String toString() { return "SummarySegment[redacted]"; }
    }

    private static void identifier(String value) { requireText(value, 128); }
    private static void text(String value) { requireText(value, 2048); }
    private static void requireText(String value, int maximum) {
        if (value == null || value.isBlank() || value.codePointCount(0, value.length()) > maximum
                || value.codePoints().anyMatch(cp -> cp >= 0xd800 && cp <= 0xdfff))
            throw invalid("SUMMARY_FIELD_INVALID");
    }
    private static void nonnegative(long value) { if (value < 0) throw invalid("SUMMARY_FIELD_INVALID"); }
    private static <T> List<T> bounded(List<T> values, int minimum, int maximum) {
        if (values == null || values.size() < minimum || values.size() > maximum) throw invalid("SUMMARY_FIELD_INVALID");
        return List.copyOf(values);
    }
    private static IllegalArgumentException invalid(String code) { return new IllegalArgumentException(code); }
}

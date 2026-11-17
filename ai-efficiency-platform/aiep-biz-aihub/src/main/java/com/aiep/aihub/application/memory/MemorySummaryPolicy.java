package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.MemorySummaryContracts.*;
import com.aiep.platformai.api.dto.MemoryContextEnvelope.Scope;
import com.aiep.platformai.api.dto.MemoryContextPacket.Dependency;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** 独立纯校验器；来源与事件必须来自可信 Java 投影，本类不认证调用方或激活候选。 */
public final class MemorySummaryPolicy {
    /** 按每个实际输入的用途交集准入；BOTH 只接受两用途范围与保留引用完全相等的保守兼容情形。 */
    public void admit(DeriveMode mode, List<SummaryInputSource> sources, Scope scope, long now) {
        require(mode != null, "SUMMARY_MODE_INVALID");
        require(sources != null && !sources.isEmpty() && sources.size() <= 128, "SUMMARY_SOURCES_INVALID");
        require(now >= 0, "SUMMARY_TIME_INVALID");
        var identities = new HashSet<List<String>>();
        for (var source : sources) {
            require(source != null, "SUMMARY_SOURCES_INVALID");
            require(identities.add(List.of(source.sourceRef().sourceType(), source.sourceRef().sourceId())), "SUMMARY_SOURCES_DUPLICATE");
        }
        long first = sources.getFirst().sequence();
        for (int index = 0; index < sources.size(); index++)
            require(sources.get(index).sequence() == first + index, "SUMMARY_SOURCE_RANGE_INVALID");
        var purposes = switch (mode) {
            case SUMMARY -> Set.of(SourcePurpose.SUMMARY);
            case PROPOSALS -> Set.of(SourcePurpose.PROPOSALS);
            case BOTH -> Set.of(SourcePurpose.SUMMARY, SourcePurpose.PROPOSALS);
        };
        for (var source : sources) {
            require(source.scope().equals(scope) && "CONVERSATION".equals(scope.sessionKind()), "SUMMARY_SCOPE_MISMATCH");
            require(source.completed(), "SUMMARY_SOURCE_INCOMPLETE");
            require(source.sourceKind() == SourceKind.ORIGINAL, "SUMMARY_RECURSION_DENIED");
            require(source.expiresAt() > now, "SUMMARY_SOURCE_EXPIRED");
            require(source.allowedPurposes().containsAll(purposes), "SUMMARY_PURPOSE_DENIED");
            require(!purposes.contains(SourcePurpose.SUMMARY)
                    || source.summaryScopeRef() != null && source.summaryRetentionRef() != null, "SUMMARY_PURPOSE_DENIED");
            require(!purposes.contains(SourcePurpose.PROPOSALS)
                    || source.proposalsScopeRef() != null && source.proposalsRetentionRef() != null, "SUMMARY_PURPOSE_DENIED");
            require(mode != DeriveMode.BOTH || source.summaryScopeRef().equals(source.proposalsScopeRef())
                    && source.summaryRetentionRef().equals(source.proposalsRetentionRef()), "SUMMARY_PURPOSE_INCOMPATIBLE");
            var group = sources.stream().filter(member -> member.groupId().equals(source.groupId())).toList();
            require(source.groupMembers().equals(group.stream().map(SummaryInputSource::sourceRef).toList()), "SUMMARY_GROUP_INCOMPLETE");
            for (int index = 0; index < group.size(); index++)
                require(group.get(index).sequence() == group.getFirst().sequence() + index, "SUMMARY_GROUP_INCOMPLETE");
            require(source.sourceDependencies().contains(source.sourceRef()), "SUMMARY_DEPENDENCIES_INCOMPLETE");
        }
    }

    /** 验证可信来源/事件与候选的联合关系，不从候选自身的状态或身份标签建立确认权威。 */
    public void validateSegment(SummarySegment segment, List<SummaryInputSource> sources,
            List<SummaryBasisEvent> events, long now, long sourceRevision) {
        admit(DeriveMode.SUMMARY, sources, segment.scope(), now);
        require(segment.coveredSources().equals(sources.stream().map(SummaryInputSource::sourceRef).toList()), "SUMMARY_COVERAGE_MISMATCH");
        require(segment.watermark().sourceRevision() == sourceRevision
                && segment.watermark().firstSequence() == sources.getFirst().sequence()
                && segment.watermark().lastSequence() == sources.getLast().sequence(), "SUMMARY_WATERMARK_MISMATCH");
        var dependencies = dependencies(sources);
        require(new HashSet<>(segment.sourceDependencies()).equals(dependencies), "SUMMARY_DEPENDENCIES_INCOMPLETE");
        require(sources.stream().allMatch(source -> segment.expiresAt() <= source.expiresAt()), "SUMMARY_EXPIRY_EXTENDED");
        require(segment.expiresAt() > now, "SUMMARY_SOURCE_EXPIRED");
        var byEvent = new HashMap<Dependency, SummaryBasisEvent>();
        for (var event : events) {
            require(dependencies.contains(event.eventRef()) && byEvent.putIfAbsent(event.eventRef(), event) == null, "SUMMARY_BASIS_UNKNOWN");
        }
        var entries = entries(segment);
        var claims = new HashMap<String, Entry>();
        for (var entry : entries) {
            var previous = claims.putIfAbsent(entry.claimRef(), entry);
            require(previous == null || previous.contentOrigin() == entry.contentOrigin()
                    && previous.decisionStatus() == entry.decisionStatus(), "SUMMARY_CLAIM_CONFLICT");
            validateEntry(entry, sources, segment.coveredSources(), byEvent);
        }
        require(segment.confirmedConstraints().stream().allMatch(entry -> entry.decisionStatus() == DecisionStatus.CONFIRMED),
                "SUMMARY_CONSTRAINT_UNCONFIRMED");
        require(segment.openQuestions().stream().allMatch(entry -> entry.decisionStatus() == DecisionStatus.UNRESOLVED)
                && segment.uncertainties().stream().allMatch(entry -> entry.decisionStatus() == DecisionStatus.UNRESOLVED),
                "SUMMARY_UNRESOLVED_STATE_CHANGED");
        for (var event : events) {
            if (event.decisionStatus() != DecisionStatus.CONFIRMED && event.decisionStatus() != DecisionStatus.REJECTED) continue;
            require(entries.stream().anyMatch(entry -> event.eventRef().equals(entry.basisEventRef())
                    && entry.decisionStatus() == event.decisionStatus()
                    && (event.decisionStatus() != DecisionStatus.REJECTED || entry instanceof RejectedOption)), "SUMMARY_REQUIRED_EVENT_MISSING");
        }
        var actualValues = new HashSet<CriticalValue>();
        entries.forEach(entry -> actualValues.addAll(entry.criticalValues()));
        var expectedValues = new HashSet<CriticalValue>();
        sources.forEach(source -> expectedValues.addAll(source.criticalValues()));
        require(actualValues.equals(expectedValues), "SUMMARY_CRITICAL_VALUES_CHANGED");
    }

    private void validateEntry(Entry entry, List<SummaryInputSource> sources, List<Dependency> covered,
            Map<Dependency, SummaryBasisEvent> byEvent) {
        require(covered.containsAll(entry.sourceRefs()), "SUMMARY_SOURCE_REF_UNKNOWN");
        var declaredSources = sources.stream().filter(source -> entry.sourceRefs().contains(source.sourceRef())).toList();
        var sourceValues = new HashSet<CriticalValue>();
        declaredSources.forEach(source -> sourceValues.addAll(source.criticalValues()));
        require(sourceValues.containsAll(entry.criticalValues()), "SUMMARY_CRITICAL_SOURCE_MISMATCH");
        var event = entry.basisEventRef() == null ? null : byEvent.get(entry.basisEventRef());
        require(entry.basisEventRef() == null || event != null, "SUMMARY_BASIS_UNKNOWN");
        if (event != null) {
            // 同段的其他独立来源不构成该条目的确认依据；真实传递依赖无需等于直接来源。
            require(dependencies(declaredSources).contains(event.eventRef()), "SUMMARY_BASIS_SOURCE_MISMATCH");
            require(entry.claimRef().equals(event.claimRef()), "SUMMARY_BASIS_CLAIM_MISMATCH");
            require(entry.decisionStatus() == event.decisionStatus(), "SUMMARY_BASIS_STATUS_MISMATCH");
        }
        if (entry.contentOrigin() == ContentOrigin.USER_REQUIREMENT || entry.contentOrigin() == ContentOrigin.BUSINESS_FACT) {
            var authority = entry.contentOrigin() == ContentOrigin.USER_REQUIREMENT ? Authority.USER : Authority.JAVA;
            require(event != null && event.authority() == authority && event.contentOrigin() == entry.contentOrigin(), "SUMMARY_AUTHORITY_REQUIRED");
        }
        if (entry.decisionStatus() == DecisionStatus.CONFIRMED || entry.decisionStatus() == DecisionStatus.REJECTED)
            require(event != null && (event.authority() == Authority.USER || event.authority() == Authority.JAVA), "SUMMARY_CONFIRMATION_REQUIRED");
        require(event == null || entry.criticalValues().equals(event.criticalValues()), "SUMMARY_CRITICAL_VALUES_CHANGED");
        if (entry instanceof RejectedOption rejected) {
            require(entry.decisionStatus() == DecisionStatus.REJECTED, "SUMMARY_REJECTED_STATUS_INVALID");
            require(event != null && Objects.equals(rejected.reason(), event.rejectionReason()), "SUMMARY_REJECTION_REASON_CHANGED");
        }
    }

    /** PENDING 仅代表候选未判旧；实时授权、持久水位与 CAS 均须后续接合，不能据此激活。 */
    public CandidateStatus candidateStatus(SummarySegment segment, List<SummaryInputSource> currentSources,
            long now, long sourceRevision) {
        if (sourceRevision < segment.watermark().sourceRevision() || segment.expiresAt() <= now) return CandidateStatus.STALE;
        var selected = currentSources.stream().filter(source -> source.sequence() >= segment.watermark().firstSequence()
                && source.sequence() <= segment.watermark().lastSequence()).toList();
        if (!selected.stream().map(SummaryInputSource::sourceRef).toList().equals(segment.coveredSources())
                || !dependencies(selected).equals(new HashSet<>(segment.sourceDependencies()))
                || selected.stream().anyMatch(source -> source.expiresAt() < segment.expiresAt())) return CandidateStatus.STALE;
        try {
            admit(DeriveMode.SUMMARY, selected, segment.scope(), now);
        } catch (IllegalArgumentException changedSource) {
            return CandidateStatus.STALE;
        }
        return CandidateStatus.PENDING;
    }

    private static Set<Dependency> dependencies(List<SummaryInputSource> sources) {
        var dependencies = new HashSet<Dependency>();
        sources.forEach(source -> dependencies.addAll(source.sourceDependencies()));
        return dependencies;
    }

    private static List<Entry> entries(SummarySegment segment) {
        var entries = new ArrayList<Entry>();
        entries.add(segment.goal()); entries.addAll(segment.confirmedConstraints()); entries.addAll(segment.decisions());
        entries.addAll(segment.rejectedOptions()); entries.addAll(segment.openQuestions());
        entries.addAll(segment.importantRefs()); entries.addAll(segment.uncertainties());
        return entries;
    }

    private static void require(boolean accepted, String code) {
        if (!accepted) throw new IllegalArgumentException(code);
    }
}

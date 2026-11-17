package com.aiep.aihub.memory;

import com.aiep.aihub.api.memory.MemorySummaryContracts.*;
import com.aiep.aihub.application.memory.MemorySummaryPolicy;
import com.aiep.platformai.api.dto.MemoryContextEnvelope.Scope;
import com.aiep.platformai.api.dto.MemoryContextPacket.Dependency;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class MemorySummaryPurposeTest {
    private final MemorySummaryPolicy policy = new MemorySummaryPolicy();
    private static final Scope SCOPE = new Scope("tenant", "user", "operations", "operations", "CONVERSATION", "s1");
    private static final Dependency M1 = ref("m1", "1", 3);
    private static final Dependency M2 = ref("m2", "1", 3);
    private static final CriticalValue AMOUNT = new CriticalValue("budget", CriticalKind.NUMBER, "100", null);
    private static final CriticalValue DATE = new CriticalValue("delivery", CriticalKind.DATE, "2026-11-18", "Asia/Shanghai");
    private static final CriticalValue NEGATION = new CriticalValue("channel", CriticalKind.CONSTRAINT, "不得发送", null);

    @Test void admitsOnlyTheIntersectionOfEveryActualInputPurpose() {
        var general = source(M1, 1);
        var sensitive = purpose(source(M2, 2), Set.of(SourcePurpose.SUMMARY), "scope", "retention");
        assertDoesNotThrow(() -> policy.admit(DeriveMode.SUMMARY, List.of(general, sensitive), SCOPE, 10));
        denied("SUMMARY_PURPOSE_DENIED", () -> policy.admit(DeriveMode.PROPOSALS, List.of(general, sensitive), SCOPE, 10));
        denied("SUMMARY_PURPOSE_DENIED", () -> policy.admit(DeriveMode.BOTH, List.of(general, sensitive), SCOPE, 10));
        assertDoesNotThrow(() -> policy.admit(DeriveMode.BOTH, List.of(general), SCOPE, 10));
    }

    @Test void bothRequiresMatchingScopeAndRetentionForEachSource() {
        for (var bad : List.of(purpose(source(M1, 1), Set.of(SourcePurpose.SUMMARY, SourcePurpose.PROPOSALS), "other", "retention"),
                purpose(source(M1, 1), Set.of(SourcePurpose.SUMMARY, SourcePurpose.PROPOSALS), "scope", "other")))
            denied("SUMMARY_PURPOSE_INCOMPATIBLE", () -> policy.admit(DeriveMode.BOTH, List.of(bad), SCOPE, 10));
        var missing = purpose(source(M1, 1), Set.of(SourcePurpose.SUMMARY, SourcePurpose.PROPOSALS), null, null);
        denied("SUMMARY_PURPOSE_DENIED", () -> policy.admit(DeriveMode.PROPOSALS, List.of(missing), SCOPE, 10));
    }

    @Test void rejectsEmptyDuplicateUnorderedAndCrossScopeInputs() {
        denied("SUMMARY_SOURCES_INVALID", () -> policy.admit(DeriveMode.SUMMARY, List.of(), SCOPE, 10));
        denied("SUMMARY_MODE_INVALID", () -> policy.admit(null, List.of(source(M1, 1)), SCOPE, 10));
        denied("SUMMARY_TIME_INVALID", () -> policy.admit(DeriveMode.SUMMARY, List.of(source(M1, 1)), SCOPE, -1));
        denied("SUMMARY_SOURCES_DUPLICATE", () -> policy.admit(DeriveMode.SUMMARY, List.of(source(M1, 1), source(M1, 2)), SCOPE, 10));
        denied("SUMMARY_SOURCES_DUPLICATE", () -> policy.admit(DeriveMode.SUMMARY, List.of(source(M1, 1), source(ref("m1", "2", 4), 2)), SCOPE, 10));
        denied("SUMMARY_SOURCE_RANGE_INVALID", () -> policy.admit(DeriveMode.SUMMARY, List.of(source(M1, 1), source(M2, 3)), SCOPE, 10));
        var other = new Scope("tenant", "other", "operations", "operations", "CONVERSATION", "s1");
        denied("SUMMARY_SCOPE_MISMATCH", () -> policy.admit(DeriveMode.SUMMARY, List.of(source(M1, 1)), other, 10));
    }

    @Test void hrTaskMaterialsCannotBecomeLongTermProfileInput() {
        var hr = new Scope("tenant", "user", "hr", "hr", "TASK_ONLY", null);
        var material = source(M1, hr, 1, "g1", List.of(M1), List.of(M1), true, SourceKind.ORIGINAL, 100, List.of());
        denied("SUMMARY_SCOPE_MISMATCH", () -> policy.admit(DeriveMode.PROPOSALS, List.of(material), hr, 10));
    }

    @Test void refusesIncompleteExpiredAndRecursiveSources() {
        denied("SUMMARY_SOURCE_INCOMPLETE", () -> policy.admit(DeriveMode.SUMMARY,
                List.of(source(M1, SCOPE, 1, "g1", List.of(M1), List.of(M1), false, SourceKind.ORIGINAL, 100, List.of())), SCOPE, 10));
        denied("SUMMARY_SOURCE_EXPIRED", () -> policy.admit(DeriveMode.SUMMARY,
                List.of(source(M1, SCOPE, 1, "g1", List.of(M1), List.of(M1), true, SourceKind.ORIGINAL, 10, List.of())), SCOPE, 10));
        denied("SUMMARY_RECURSION_DENIED", () -> policy.admit(DeriveMode.SUMMARY,
                List.of(source(M1, SCOPE, 1, "g1", List.of(M1), List.of(M1), true, SourceKind.SUMMARY, 100, List.of())), SCOPE, 10));
    }

    @Test void keepsWholeToolGroupsWithoutInterleaving() {
        var first = source(M1, SCOPE, 1, "tool", List.of(M1, M2), List.of(M1), true, SourceKind.ORIGINAL, 100, List.of());
        denied("SUMMARY_GROUP_INCOMPLETE", () -> policy.admit(DeriveMode.SUMMARY, List.of(first), SCOPE, 10));
        var second = source(M2, SCOPE, 2, "tool", List.of(M1, M2), List.of(M2), true, SourceKind.ORIGINAL, 100, List.of());
        assertDoesNotThrow(() -> policy.admit(DeriveMode.SUMMARY, List.of(first, second), SCOPE, 10));
        var third = ref("m3", "1", 3);
        var interleaved = List.of(source(M1, SCOPE, 1, "tool", List.of(M1, third), List.of(M1), true, SourceKind.ORIGINAL, 100, List.of()),
                source(M2, 2), source(third, SCOPE, 3, "tool", List.of(M1, third), List.of(third), true, SourceKind.ORIGINAL, 100, List.of()));
        denied("SUMMARY_GROUP_INCOMPLETE", () -> policy.admit(DeriveMode.SUMMARY, interleaved, SCOPE, 10));
    }

    @Test void requiresTheFullInputDependencyClosure() {
        var dependency = ref("parent", "1", 3);
        var input = source(M1, SCOPE, 1, "g1", List.of(M1), List.of(M1, dependency), true, SourceKind.ORIGINAL, 100, List.of());
        denied("SUMMARY_DEPENDENCIES_INCOMPLETE", () -> validate(segment(List.of(M1), List.of(M1), goal(), List.of(), List.of(), List.of(), List.of(), List.of(), List.of(), 100), List.of(input), List.of()));
        var missingSelf = source(M1, SCOPE, 1, "g1", List.of(M1), List.of(dependency), true, SourceKind.ORIGINAL, 100, List.of());
        denied("SUMMARY_DEPENDENCIES_INCOMPLETE", () -> policy.admit(DeriveMode.SUMMARY, List.of(missingSelf), SCOPE, 10));
    }

    @Test void modelSuggestionCannotConfirmItselfOrUseModelAuthority() {
        var decision = entry("option-A", ContentOrigin.MODEL_SUGGESTION, DecisionStatus.CONFIRMED, List.of(M1), null, List.of());
        denied("SUMMARY_CONFIRMATION_REQUIRED", () -> validate(decisions(decision), List.of(source(M1, 1)), List.of()));
        var withBasis = entry("option-A", ContentOrigin.MODEL_SUGGESTION, DecisionStatus.CONFIRMED, List.of(M1), M1, List.of());
        var model = event(M1, "option-A", Authority.MODEL, ContentOrigin.MODEL_SUGGESTION, DecisionStatus.CONFIRMED, List.of(), null);
        denied("SUMMARY_CONFIRMATION_REQUIRED", () -> validate(decisions(withBasis), List.of(source(M1, 1)), List.of(model)));
    }

    @Test void explicitUserConfirmationKeepsTheOriginalSuggestionOrigin() {
        var decision = entry("option-A", ContentOrigin.MODEL_SUGGESTION, DecisionStatus.CONFIRMED, List.of(M1), M1, List.of());
        var user = event(M1, "option-A", Authority.USER, ContentOrigin.USER_REQUIREMENT, DecisionStatus.CONFIRMED, List.of(), null);
        assertDoesNotThrow(() -> validate(decisions(decision), List.of(source(M1, 1)), List.of(user)));
        assertEquals(ContentOrigin.MODEL_SUGGESTION, decision.contentOrigin());
    }

    @Test void eachEntryBasisMustBelongToItsOwnSourcesNotAnotherCoveredSource() {
        var borrowed = entry("option-A", ContentOrigin.MODEL_SUGGESTION, DecisionStatus.CONFIRMED, List.of(M2), M1, List.of());
        var segment = segment(List.of(M1, M2), List.of(M1, M2), goal(), List.of(), List.of(borrowed), List.of(), List.of(), List.of(), List.of(), 100);
        var user = event(M1, "option-A", Authority.USER, ContentOrigin.USER_REQUIREMENT, DecisionStatus.CONFIRMED, List.of(), null);
        denied("SUMMARY_BASIS_SOURCE_MISMATCH", () -> validate(segment, List.of(source(M1, 1), source(M2, 2)), List.of(user)));
    }

    @Test void aRealTransitiveConfirmationDoesNotHaveToEqualTheDirectSourceRef() {
        var confirmation = ref("confirmation", "2", 4);
        var input = source(M1, SCOPE, 1, "g1", List.of(M1), List.of(M1, confirmation), true, SourceKind.ORIGINAL, 100, List.of());
        var decision = entry("option-A", ContentOrigin.MODEL_SUGGESTION, DecisionStatus.CONFIRMED, List.of(M1), confirmation, List.of());
        var segment = segment(List.of(M1), List.of(M1, confirmation), goal(), List.of(), List.of(decision), List.of(), List.of(), List.of(), List.of(), 100);
        assertDoesNotThrow(() -> validate(segment, List.of(input), List.of(event(confirmation, "option-A", Authority.USER,
                ContentOrigin.USER_REQUIREMENT, DecisionStatus.CONFIRMED, List.of(), null))));
    }

    @Test void everyBasisStatusIncludingUnconfirmedStatesMustMatch() {
        for (var status : List.of(DecisionStatus.PROPOSED, DecisionStatus.UNRESOLVED)) {
            var mismatch = status == DecisionStatus.PROPOSED ? DecisionStatus.UNRESOLVED : DecisionStatus.PROPOSED;
            var decision = entry("option-A", ContentOrigin.MODEL_SUGGESTION, status, List.of(M1), M1, List.of());
            denied("SUMMARY_BASIS_STATUS_MISMATCH", () -> validate(decisions(decision), List.of(source(M1, 1)),
                    List.of(event(M1, "option-A", Authority.MODEL, ContentOrigin.MODEL_SUGGESTION, mismatch, List.of(), null))));
            assertDoesNotThrow(() -> validate(decisions(decision), List.of(source(M1, 1)),
                    List.of(event(M1, "option-A", Authority.MODEL, ContentOrigin.MODEL_SUGGESTION, status, List.of(), null))));
        }
    }

    @Test void userRequirementsAndBusinessFactsNeedTheCorrespondingTrustedAuthority() {
        for (var origin : List.of(ContentOrigin.USER_REQUIREMENT, ContentOrigin.BUSINESS_FACT)) {
            var decision = entry("fact", origin, DecisionStatus.PROPOSED, List.of(M1), M1, List.of());
            var correct = origin == ContentOrigin.USER_REQUIREMENT ? Authority.USER : Authority.JAVA;
            var wrong = correct == Authority.USER ? Authority.JAVA : Authority.USER;
            denied("SUMMARY_AUTHORITY_REQUIRED", () -> validate(decisions(decision), List.of(source(M1, 1)),
                    List.of(event(M1, "fact", wrong, origin, DecisionStatus.PROPOSED, List.of(), null))));
            assertDoesNotThrow(() -> validate(decisions(decision), List.of(source(M1, 1)),
                    List.of(event(M1, "fact", correct, origin, DecisionStatus.PROPOSED, List.of(), null))));
        }
    }

    @Test void rejectsUnknownSourcesEventsAndClaimSubstitution() {
        var unknownSource = entry("option-A", ContentOrigin.MODEL_SUGGESTION, DecisionStatus.PROPOSED, List.of(M2), null, List.of());
        denied("SUMMARY_SOURCE_REF_UNKNOWN", () -> validate(decisions(unknownSource), List.of(source(M1, 1)), List.of()));
        var unknownEvent = entry("option-A", ContentOrigin.MODEL_SUGGESTION, DecisionStatus.PROPOSED, List.of(M1), M2, List.of());
        denied("SUMMARY_BASIS_UNKNOWN", () -> validate(decisions(unknownEvent), List.of(source(M1, 1)), List.of()));
        var wrongClaim = entry("option-A", ContentOrigin.MODEL_SUGGESTION, DecisionStatus.PROPOSED, List.of(M1), M1, List.of());
        denied("SUMMARY_BASIS_CLAIM_MISMATCH", () -> validate(decisions(wrongClaim), List.of(source(M1, 1)),
                List.of(event(M1, "another", Authority.MODEL, ContentOrigin.MODEL_SUGGESTION, DecisionStatus.PROPOSED, List.of(), null))));
    }

    @Test void knownRejectionReasonIsPreservedAndUnknownReasonIsNeverInvented() {
        for (String reason : new String[]{"预算不允许", null}) {
            var rejected = rejection(reason);
            var trusted = event(M1, "option-A", Authority.USER, ContentOrigin.USER_REQUIREMENT, DecisionStatus.REJECTED, List.of(), reason);
            assertDoesNotThrow(() -> validate(rejected(rejected), List.of(source(M1, 1)), List.of(trusted)));
            denied("SUMMARY_REJECTION_REASON_CHANGED", () -> validate(rejected(rejection("模型编造原因")), List.of(source(M1, 1)), List.of(trusted)));
        }
    }

    @Test void confirmedAndRejectedEventsCannotDisappearFromTheSummary() {
        for (var status : List.of(DecisionStatus.CONFIRMED, DecisionStatus.REJECTED)) {
            var trusted = event(M1, "option-A", Authority.USER, ContentOrigin.USER_REQUIREMENT, status, List.of(), null);
            denied("SUMMARY_REQUIRED_EVENT_MISSING", () -> validate(empty(), List.of(source(M1, 1)), List.of(trusted)));
        }
        var misplaced = entry("option-A", ContentOrigin.MODEL_SUGGESTION, DecisionStatus.REJECTED, List.of(M1), M1, List.of());
        denied("SUMMARY_REQUIRED_EVENT_MISSING", () -> validate(decisions(misplaced), List.of(source(M1, 1)),
                List.of(event(M1, "option-A", Authority.USER, ContentOrigin.USER_REQUIREMENT, DecisionStatus.REJECTED, List.of(), null))));
    }

    @Test void preservesTypedNumbersDatesAndNegativeConstraintsAsGoldenExample() {
        var values = List.of(AMOUNT, DATE, NEGATION);
        var input = source(M1, SCOPE, 1, "g1", List.of(M1), List.of(M1), true, SourceKind.ORIGINAL, 100, values);
        var constraint = entry("limits", ContentOrigin.USER_REQUIREMENT, DecisionStatus.CONFIRMED, List.of(M1), M1, values);
        var trusted = event(M1, "limits", Authority.USER, ContentOrigin.USER_REQUIREMENT, DecisionStatus.CONFIRMED, values, null);
        var golden = segment(List.of(M1), List.of(M1), goal(), List.of(constraint), List.of(), List.of(), List.of(), List.of(), List.of(), 100);
        assertDoesNotThrow(() -> validate(golden, List.of(input), List.of(trusted)));
        assertEquals("Asia/Shanghai", golden.confirmedConstraints().getFirst().criticalValues().get(1).timezone());
        var changed = entry("limits", ContentOrigin.USER_REQUIREMENT, DecisionStatus.CONFIRMED, List.of(M1), M1, List.of(AMOUNT, DATE));
        denied("SUMMARY_CRITICAL_VALUES_CHANGED", () -> validate(decisions(changed), List.of(input), List.of(trusted)));
        denied("SUMMARY_CRITICAL_VALUES_CHANGED", () -> validate(empty(), List.of(input), List.of()));
        denied("SUMMARY_CRITICAL_SOURCE_MISMATCH", () -> validate(decisions(constraint), List.of(source(M1, 1)), List.of(trusted)));
    }

    @Test void criticalFieldIdentityAndDateTimezoneCannotBeSilentlyRewritten() {
        denied("SUMMARY_DATE_TIMEZONE_REQUIRED", () -> new CriticalValue("date", CriticalKind.DATE, "2026-11-18", null));
        denied("SUMMARY_DATE_TIMEZONE_INVALID", () -> new CriticalValue("date", CriticalKind.DATE, "2026-11-18", "Not/AZone"));
        denied("SUMMARY_DATE_TIMEZONE_INVALID", () -> new CriticalValue("number", CriticalKind.NUMBER, "1", "Asia/Shanghai"));
        var changedField = new CriticalValue("another-field", CriticalKind.NUMBER, "100", null);
        var decision = entry("fact", ContentOrigin.MODEL_SUGGESTION, DecisionStatus.PROPOSED, List.of(M1), null, List.of(changedField));
        var input = source(M1, SCOPE, 1, "g1", List.of(M1), List.of(M1), true, SourceKind.ORIGINAL, 100, List.of(AMOUNT));
        denied("SUMMARY_CRITICAL_SOURCE_MISMATCH", () -> validate(decisions(decision), List.of(input), List.of()));
    }

    @Test void rejectsChangedCoverageWatermarkAndExtendedExpiry() {
        var two = List.of(source(M1, 1), source(M2, 2));
        denied("SUMMARY_COVERAGE_MISMATCH", () -> validate(empty(), two, List.of()));
        denied("SUMMARY_WATERMARK_MISMATCH", () -> policy.validateSegment(empty(), List.of(source(M1, 1)), List.of(), 10, 2));
        var extended = segment(List.of(M1), List.of(M1), goal(), List.of(), List.of(), List.of(), List.of(), List.of(), List.of(), 101);
        denied("SUMMARY_EXPIRY_EXTENDED", () -> validate(extended, List.of(source(M1, 1)), List.of()));
        var expired = segment(List.of(M1), List.of(M1), goal(), List.of(), List.of(), List.of(), List.of(), List.of(), List.of(), 10);
        denied("SUMMARY_SOURCE_EXPIRED", () -> validate(expired, List.of(source(M1, 1)), List.of()));
    }

    @Test void unresolvedSlotsAndConfirmedConstraintsKeepTheirDecisionStates() {
        var proposed = entry("option-A", ContentOrigin.MODEL_SUGGESTION, DecisionStatus.PROPOSED, List.of(M1), null, List.of());
        var badConstraint = segment(List.of(M1), List.of(M1), goal(), List.of(proposed), List.of(), List.of(), List.of(), List.of(), List.of(), 100);
        denied("SUMMARY_CONSTRAINT_UNCONFIRMED", () -> validate(badConstraint, List.of(source(M1, 1)), List.of()));
        for (boolean question : List.of(true, false)) {
            var badOpen = segment(List.of(M1), List.of(M1), goal(), List.of(), List.of(), List.of(), question ? List.of(proposed) : List.of(), List.of(), question ? List.of() : List.of(proposed), 100);
            denied("SUMMARY_UNRESOLVED_STATE_CHANGED", () -> validate(badOpen, List.of(source(M1, 1)), List.of()));
        }
        var conflict = entry("goal", ContentOrigin.UNCONFIRMED_INFERENCE, DecisionStatus.PROPOSED, List.of(M1), null, List.of());
        denied("SUMMARY_CLAIM_CONFLICT", () -> validate(decisions(conflict), List.of(source(M1, 1)), List.of()));
    }

    @Test void staleTracksOldSourceChangesButAllowsAppendsBeyondTheWatermark() {
        assertEquals(CandidateStatus.PENDING, policy.candidateStatus(empty(), List.of(source(M1, 1), source(M2, 2)), 10, 2));
        assertEquals(CandidateStatus.STALE, policy.candidateStatus(empty(), List.of(source(ref("m1", "2", 3), 1)), 10, 2));
        assertEquals(CandidateStatus.STALE, policy.candidateStatus(empty(), List.of(source(ref("m1", "1", 4), 1)), 10, 2));
        assertEquals(CandidateStatus.STALE, policy.candidateStatus(empty(), List.of(), 10, 2));
        assertEquals(CandidateStatus.STALE, policy.candidateStatus(empty(), List.of(source(M1, 1)), 10, 0));
        assertEquals(CandidateStatus.STALE, policy.candidateStatus(empty(), List.of(source(M1, 1)), 100, 2));
        var changed = source(M1, SCOPE, 1, "g1", List.of(M1), List.of(M1, M2), true, SourceKind.ORIGINAL, 100, List.of());
        assertEquals(CandidateStatus.STALE, policy.candidateStatus(empty(), List.of(changed), 10, 2));
        var shortened = source(M1, SCOPE, 1, "g1", List.of(M1), List.of(M1), true, SourceKind.ORIGINAL, 50, List.of());
        assertEquals(CandidateStatus.STALE, policy.candidateStatus(empty(), List.of(shortened), 10, 2));
        var expandedGroup = source(M1, SCOPE, 1, "g1", List.of(M1, M2), List.of(M1), true, SourceKind.ORIGINAL, 100, List.of());
        assertEquals(CandidateStatus.STALE, policy.candidateStatus(empty(), List.of(expandedGroup, source(M2, 2)), 10, 2));
    }

    @Test void contractsAreBoundedImmutableAndNeverRenderNarrativeOrSensitiveValues() {
        var original = new ArrayList<>(List.of(M1));
        var entry = entry("fact", ContentOrigin.MODEL_SUGGESTION, DecisionStatus.PROPOSED, original, null, List.of(AMOUNT));
        original.clear();
        assertEquals(List.of(M1), entry.sourceRefs());
        assertThrows(UnsupportedOperationException.class, () -> entry.sourceRefs().clear());
        assertFalse(entry.toString().contains("建议方案A"));
        assertFalse(AMOUNT.toString().contains("100"));
        assertFalse(rejection("不宜展示的原因").toString().contains("不宜展示"));
        denied("SUMMARY_FIELD_INVALID", () -> entry("x".repeat(129), ContentOrigin.MODEL_SUGGESTION, DecisionStatus.PROPOSED, List.of(M1), null, List.of()));
        denied("SUMMARY_FIELD_INVALID", () -> new SummaryEntry("claim", "x".repeat(2049), ContentOrigin.MODEL_SUGGESTION, DecisionStatus.PROPOSED, List.of(M1), null, List.of()));
    }

    private void validate(SummarySegment segment, List<SummaryInputSource> sources, List<SummaryBasisEvent> events) {
        policy.validateSegment(segment, sources, events, 10, 1);
    }
    private static void denied(String code, org.junit.jupiter.api.function.Executable action) {
        assertEquals(code, assertThrows(IllegalArgumentException.class, action).getMessage());
    }
    private static Dependency ref(String id, String version, long epoch) { return new Dependency("MESSAGE", id, version, 2, epoch, 4); }
    private static SummaryInputSource source(Dependency ref, long sequence) {
        return source(ref, SCOPE, sequence, "g-" + ref.sourceId(), List.of(ref), List.of(ref), true, SourceKind.ORIGINAL, 100, List.of());
    }
    private static SummaryInputSource source(Dependency ref, Scope scope, long sequence, String group, List<Dependency> members,
            List<Dependency> dependencies, boolean completed, SourceKind kind, long expires, List<CriticalValue> values) {
        return new SummaryInputSource(ref, scope, sequence, group, members, dependencies, completed, kind,
                Set.of(SourcePurpose.SUMMARY, SourcePurpose.PROPOSALS), "scope", "scope", "retention", "retention", expires, values);
    }
    private static SummaryInputSource purpose(SummaryInputSource input, Set<SourcePurpose> purposes, String scope, String retention) {
        return new SummaryInputSource(input.sourceRef(), input.scope(), input.sequence(), input.groupId(), input.groupMembers(),
                input.sourceDependencies(), input.completed(), input.sourceKind(), purposes, input.summaryScopeRef(), scope,
                input.summaryRetentionRef(), retention, input.expiresAt(), input.criticalValues());
    }
    private static SummaryEntry entry(String claim, ContentOrigin origin, DecisionStatus status, List<Dependency> refs,
            Dependency basis, List<CriticalValue> values) {
        return new SummaryEntry(claim, "建议方案A", origin, status, refs, basis, values);
    }
    private static SummaryEntry goal() { return entry("goal", ContentOrigin.MODEL_SUGGESTION, DecisionStatus.PROPOSED, List.of(M1), null, List.of()); }
    private static SummarySegment empty() { return decisions(); }
    private static SummarySegment decisions(SummaryEntry... entries) {
        return segment(List.of(M1), List.of(M1), goal(), List.of(), List.of(entries), List.of(), List.of(), List.of(), List.of(), 100);
    }
    private static RejectedOption rejection(String reason) {
        return new RejectedOption("option-A", "否决A", ContentOrigin.MODEL_SUGGESTION, DecisionStatus.REJECTED, List.of(M1), M1, List.of(), reason);
    }
    private static SummarySegment rejected(RejectedOption entry) {
        return segment(List.of(M1), List.of(M1), goal(), List.of(), List.of(), List.of(entry), List.of(), List.of(), List.of(), 100);
    }
    private static SummarySegment segment(List<Dependency> covered, List<Dependency> dependencies, SummaryEntry goal,
            List<SummaryEntry> constraints, List<SummaryEntry> decisions, List<RejectedOption> rejected,
            List<SummaryEntry> questions, List<SummaryEntry> refs, List<SummaryEntry> uncertainties, long expires) {
        return new SummarySegment("seg1", SCOPE, covered, new SummaryWatermark(1, 1, covered.size()), goal,
                constraints, decisions, rejected, questions, refs, uncertainties, dependencies, expires);
    }
    private static SummaryBasisEvent event(Dependency ref, String claim, Authority authority, ContentOrigin origin,
            DecisionStatus status, List<CriticalValue> values, String reason) {
        return new SummaryBasisEvent(ref, claim, authority, origin, status, values, reason);
    }
}

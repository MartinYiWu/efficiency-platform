package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.api.hr.HrPositionContracts.*;
import com.aiep.aihub.domain.hr.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Component;

@Component
public class HrResultAssembler {
  public Matching project(com.aiep.aihub.api.hr.HrActor actor, Matching matching) {
    return marks == null ? matching : withMarks(matching, marks.project(actor, matching));
  }

  private final HrSpecialMarksService marks;

  public HrResultAssembler() {
    this.marks = null;
  }

  @org.springframework.beans.factory.annotation.Autowired
  public HrResultAssembler(HrSpecialMarksService marks) {
    this.marks = marks;
  }

  public Matching assemble(
      com.aiep.aihub.api.hr.HrActor actor,
      String id,
      Facts facts,
      String factSnapshotId,
      Position position,
      ConfigVersion config,
      String semanticId,
      HrScoreResult score,
      List<HrAtomicAssessment> assessments) {
    var initial =
        assemble(id, facts, factSnapshotId, position, config, semanticId, score, assessments);
    return withMarks(
        initial,
        marks == null
            ? initial.specialMarks()
            : marks.calculate(
                actor,
                facts,
                initial.hardConditions(),
                score.reasonCodes(),
                initial.band(),
                config.snapshot().visibleMarks()));
  }

  public Matching assemble(
      String id,
      Facts facts,
      String factSnapshotId,
      Position position,
      ConfigVersion config,
      String semanticId,
      HrScoreResult score,
      List<HrAtomicAssessment> assessments) {
    Map<String, HrAtomicAssessment> byId = new HashMap<>();
    for (var a : assessments) byId.put(a.requirementId(), a);
    List<DimensionView> dimensions = new ArrayList<>();
    for (var d : HrFrozenConfig.Dimension.values()) {
      var s = score.dimensions().get(d);
      var requirements =
          config.snapshot().scoring().requirements().stream()
              .filter(r -> r.dimension() == d)
              .map(
                  r -> {
                    var a = byId.get(r.id());
                    String label =
                        config.snapshot().criteria().stream()
                            .filter(c -> c.id().equals(r.id()))
                            .map(SemanticCriterion::label)
                            .findFirst()
                            .orElse(r.id());
                    return new RequirementView(
                        r.id(), label, a.level().name(), null, a.evidenceIds());
                  })
              .toList();
      dimensions.add(
          new DimensionView(
              d.name(),
              d.name(),
              s == null ? null : s.score(),
              config.snapshot().scoring().weights().get(d),
              s == null || s.coverage() == null ? BigDecimal.ZERO : s.coverage(),
              requirements));
    }
    List<HardConditionView> hard =
        score.hardConditions().stream()
            .map(
                h -> {
                  var rule =
                      config.snapshot().hardConditions().stream()
                          .filter(r -> r.id().equals(h.id()))
                          .findFirst()
                          .orElseThrow();
                  return new HardConditionView(
                      h.id(),
                      rule.label(),
                      h.status().name(),
                      rule.expected(),
                      HrFactMeasurements.actual(rule,facts,score.asOfDate(),h.status().name()),
                      h.overrideAllowed() && rule.overridable());
                })
            .toList();
    return new Matching(
        id,
        facts.candidateId(),
        facts.profile().name(),
        position.id(),
        position.name(),
        factSnapshotId,
        config.version(),
        config.contextVersion(),
        semanticId,
        score.asOfDate().toString(),
        score.businessStatus().name(),
        score.totalScore() == null ? "UNAVAILABLE" : "SCORED",
        score.totalScore(),
        score.referenceScore(),
        score.evidenceCoverage() == null ? BigDecimal.ZERO : score.evidenceCoverage(),
        score.band() == null ? null : score.band().name(),
        score.reasonCodes(),
        dimensions,
        hard,
        List.of(),
        HrPositionService.hash(List.of(factSnapshotId, config.snapshotHash(), semanticId)),
        Instant.now().toString(),
        null,
        List.of(),
        score.reasonCodes(),
        List.of(
            config.snapshot().scoring().highThreshold(),
            config.snapshot().scoring().middleThreshold(),
            config.snapshot().scoring().lowThreshold()),
        facts.pageCount(),
        facts.blocks(),
        new Explanation(List.of(), List.of(), "NOT_REQUESTED"),
        HrSpecialMarksService.basic(
            facts,
            hard,
            score.reasonCodes(),
            score.band() == null ? null : score.band().name(),
            config.snapshot().visibleMarks()));
  }

  public Matching status(Matching m, String status, String supersededBy) {
    return new Matching(
        m.resultId(),
        m.candidateId(),
        m.candidateName(),
        m.positionId(),
        m.positionName(),
        m.factSnapshotId(),
        m.configVersion(),
        m.contextVersion(),
        m.semanticSnapshotId(),
        m.asOfDate(),
        status.equals("CURRENT")||status.equals("TEMPORARY") ? m.businessStatus() : status,
        m.scoreStatus(),
        m.totalScore(),
        m.referenceScore(),
        m.evidenceCoverage(),
        m.band(),
        m.reasonCodes(),
        m.dimensions(),
        m.hardConditions(),
        m.overrides(),
        m.snapshotHash(),
        m.createdAt(),
        supersededBy,
        m.highlights(),
        m.reviewPoints(),
        m.thresholds(),
        m.pageCount(),
        m.blocks(),
        m.explanation(),
        m.specialMarks());
  }

  public Matching details(Matching m, Explanation explanation, List<OverrideView> overrides) {
    return new Matching(
        m.resultId(),
        m.candidateId(),
        m.candidateName(),
        m.positionId(),
        m.positionName(),
        m.factSnapshotId(),
        m.configVersion(),
        m.contextVersion(),
        m.semanticSnapshotId(),
        m.asOfDate(),
        m.businessStatus(),
        m.scoreStatus(),
        m.totalScore(),
        m.referenceScore(),
        m.evidenceCoverage(),
        m.band(),
        m.reasonCodes(),
        m.dimensions(),
        m.hardConditions(),
        List.copyOf(overrides),
        HrPositionService.hash(List.of(m.snapshotHash(), overrides)),
        m.createdAt(),
        m.supersededBy(),
        explanation.highlights().stream().map(ExplanationItem::text).toList(),
        explanation.verificationPoints().stream().map(ExplanationItem::text).toList(),
        m.thresholds(),
        m.pageCount(),
        m.blocks(),
        explanation,
        m.specialMarks());
  }

  public Matching evidence(Matching m, List<SemanticAssessment> assessments) {
    Map<String, SemanticAssessment> source = new HashMap<>();
    for (SemanticAssessment assessment : assessments)
      source.put(assessment.requirementId(), assessment);
    List<DimensionView> dimensions =
        m.dimensions().stream()
            .map(
                d ->
                    new DimensionView(
                        d.id(),
                        d.label(),
                        d.score(),
                        d.weight(),
                        d.evidenceCoverage(),
                        d.requirements().stream()
                            .map(
                                r -> {
                                  SemanticAssessment assessment = source.get(r.id());
                                  String quote =
                                      assessment == null || assessment.evidence().isEmpty()
                                          ? null
                                          : assessment.evidence().stream()
                                              .map(Evidence::quote)
                                              .collect(java.util.stream.Collectors.joining("\n"));
                                  return new RequirementView(
                                      r.id(), r.label(), r.judgment(), quote, r.evidenceIds());
                                })
                            .toList()))
            .toList();
    List<HardConditionView> hard=m.hardConditions().stream().map(h->{if(h.actual()!=null)return h;Set<String> ids=new HashSet<>();ids.add(h.id());for(int index=0;index<60;index++)ids.add("hard-"+HrPositionService.hash(List.of(h.id(),index)).substring(0,32));List<String> quotes=assessments.stream().filter(item->ids.contains(item.requirementId())).flatMap(item->item.evidence().stream()).filter(e->m.blocks().stream().anyMatch(b->b.id().equals(e.blockId())&&exact(b.text(),e))).map(Evidence::quote).distinct().limit(5).toList();String actual=quotes.isEmpty()?null:String.join("；",quotes);return new HardConditionView(h.id(),h.label(),h.status(),h.expected(),actual,h.overridable());}).toList();
    return new Matching(
        m.resultId(),
        m.candidateId(),
        m.candidateName(),
        m.positionId(),
        m.positionName(),
        m.factSnapshotId(),
        m.configVersion(),
        m.contextVersion(),
        m.semanticSnapshotId(),
        m.asOfDate(),
        m.businessStatus(),
        m.scoreStatus(),
        m.totalScore(),
        m.referenceScore(),
        m.evidenceCoverage(),
        m.band(),
        m.reasonCodes(),
        dimensions,
        hard,
        m.overrides(),
        m.snapshotHash(),
        m.createdAt(),
        m.supersededBy(),
        m.highlights(),
        m.reviewPoints(),
        m.thresholds(),
        m.pageCount(),
        m.blocks(),
        m.explanation(),
        m.specialMarks());
  }

  private static boolean exact(String text,Evidence evidence){if(text==null||evidence.start()<0||evidence.end()<=evidence.start()||evidence.end()>text.codePointCount(0,text.length()))return false;return text.substring(text.offsetByCodePoints(0,evidence.start()),text.offsetByCodePoints(0,evidence.end())).equals(evidence.quote());}

  public Matching withMarks(Matching m, List<SpecialMark> marks) {
    return new Matching(
        m.resultId(),
        m.candidateId(),
        m.candidateName(),
        m.positionId(),
        m.positionName(),
        m.factSnapshotId(),
        m.configVersion(),
        m.contextVersion(),
        m.semanticSnapshotId(),
        m.asOfDate(),
        m.businessStatus(),
        m.scoreStatus(),
        m.totalScore(),
        m.referenceScore(),
        m.evidenceCoverage(),
        m.band(),
        m.reasonCodes(),
        m.dimensions(),
        m.hardConditions(),
        m.overrides(),
        m.snapshotHash(),
        m.createdAt(),
        m.supersededBy(),
        m.highlights(),
        m.reviewPoints(),
        m.thresholds(),
        m.pageCount(),
        m.blocks(),
        m.explanation(),
        marks);
  }
}

package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrPositionContracts.*;
import com.aiep.aihub.domain.hr.HrFrozenConfig;
import java.math.BigDecimal;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 仅从明确FAIL复制冻结标准到未发布草稿，既有配置、事实和结果完全不重写。 */
@Service
public class HrSoftRuleDraftService {
  public record Request(String conditionId, long expectedPositionVersion, String reason) {}

  private final HrPositionService positions;
  private final HrMatchingService matching;
  private final HrAuditService audit;

  public HrSoftRuleDraftService(
      HrPositionService positions, HrMatchingService matching, HrAuditService audit) {
    this.positions = positions;
    this.matching = matching;
    this.audit = audit;
  }

  @Transactional
  public Draft create(HrActor actor, String resultId, Request request) {
    HrCandidateMergeService.reason(request.reason());
    var result = matching.get(actor, resultId);
    var failed =
        result.hardConditions().stream()
            .filter(h -> Objects.equals(h.id(), request.conditionId()) && "FAIL".equals(h.status()))
            .findFirst()
            .orElseThrow(
                () ->
                    new HrBusinessException(
                        "HR_SOFT_DRAFT_EXPLICIT_FAIL_REQUIRED", "只能将原结果明确失败的硬条件转为草稿", 422));
    var position = positions.get(actor, result.positionId());
    HrAccessPolicy.requireFor(
        actor, "hr:position:edit", position.departmentId(), position.id(), "POSITION");
    var draft = positions.draft(actor, position.id());
    if (position.version() != request.expectedPositionVersion()
        || draft.version() != request.expectedPositionVersion())
      throw HrCandidateMergeService.conflict();
    var frozen = positions.config(actor, position.id(), result.configVersion()).snapshot();
    var rule =
        frozen.hardConditions().stream()
            .filter(h -> h.id().equals(failed.id()))
            .findFirst()
            .orElseThrow(HrTalentSearchService::missing);
    if (draft.hardConditions().stream().noneMatch(h -> h.id().equals(rule.id())))
      throw new HrBusinessException("HR_SOFT_DRAFT_CONDITION_CHANGED", "当前草稿已移除此硬条件，请检查草稿", 409);
    var anchor =
        frozen.criteria().stream().filter(c -> c.id().equals(rule.id())).findFirst().orElse(null);
    HrFrozenConfig.Dimension dimension = dimension(rule, anchor);
    String id = "soft-" + UUID.randomUUID();
    var criterion =
        new SemanticCriterion(
            id,
            anchor == null ? rule.label() : anchor.label(),
            dimension.name(),
            anchor == null ? Objects.toString(rule.expected(), rule.label()) : anchor.criterion(),
            anchor == null ? "" : anchor.strongAnchor(),
            anchor == null ? "" : anchor.matchAnchor(),
            anchor == null ? "" : anchor.partialAnchor(),
            anchor == null ? "" : anchor.notMetAnchor(),
            false,
            anchor == null ? null : anchor.calculation());
    DraftScoring old = scoring(draft);
    List<HrFrozenConfig.Requirement> requirements =
        new ArrayList<>(old.requirements() == null ? List.of() : old.requirements());
    requirements.add(new HrFrozenConfig.Requirement(id, dimension, BigDecimal.ONE, false, true));
    Set<String> retained =
        requirements.stream()
            .map(HrFrozenConfig.Requirement::id)
            .collect(java.util.stream.Collectors.toSet());
    List<SemanticCriterion> criteria =
        new ArrayList<>(
            draft.criteria().stream()
                .filter(c -> !c.id().equals(rule.id()) || retained.contains(c.id()))
                .toList());
    criteria.add(criterion);
    var next =
        new Draft(
            draft.positionId(),
            draft.name(),
            draft.family(),
            draft.departmentId(),
            draft.level(),
            draft.jdText(),
            "SOFT_REQUIREMENTS",
            null,
            draft.hardConditions().stream().filter(h -> !h.id().equals(rule.id())).toList(),
            List.copyOf(criteria),
            draft.version(),
            new DraftScoring(
                "draft",
                old.weights(),
                List.copyOf(requirements),
                old.highThreshold(),
                old.middleThreshold(),
                old.lowThreshold(),
                old.minimumCoverage(),
                old.strongCoverage()),
            draft.visibleMarks());
    Draft saved = positions.save(actor, position.id(), next);
    audit.append(actor, "HARD_CONDITION_TO_SOFT_DRAFT", resultId, position.departmentId());
    return saved;
  }

  private DraftScoring scoring(Draft draft) {
    if (draft.draftScoring() != null) return draft.draftScoring();
    var c = draft.scoring();
    return c == null
        ? new DraftScoring("draft", null, List.of(), null, null, null, null, null)
        : new DraftScoring(
            "draft",
            c.weights(),
            c.requirements(),
            c.highThreshold(),
            c.middleThreshold(),
            c.lowThreshold(),
            c.minimumCoverage(),
            c.strongCoverage());
  }

  private HrFrozenConfig.Dimension dimension(HardRule rule, SemanticCriterion anchor) {
    if (anchor != null) {
      try {
        return HrFrozenConfig.Dimension.valueOf(anchor.dimension());
      } catch (IllegalArgumentException ignored) {
      }
    }
    return switch (rule.type()) {
      case "EDUCATION" -> HrFrozenConfig.Dimension.EDUCATION;
      case "WORK_EXPERIENCE" -> HrFrozenConfig.Dimension.EXPERIENCE;
      case "PROJECT_SCALE", "TEAM_SIZE" -> HrFrozenConfig.Dimension.PROJECT;
      case "REQUIRED_SKILL", "LANGUAGE" -> HrFrozenConfig.Dimension.SKILL;
      default -> HrFrozenConfig.Dimension.BONUS;
    };
  }
}

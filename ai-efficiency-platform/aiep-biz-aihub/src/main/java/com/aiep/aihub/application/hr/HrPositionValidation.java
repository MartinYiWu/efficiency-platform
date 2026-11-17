package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrPositionContracts.Draft;
import com.aiep.aihub.api.hr.HrPositionContracts.HardRule;
import com.aiep.aihub.api.hr.HrPositionContracts.SemanticCriterion;
import com.aiep.aihub.domain.hr.HrFrozenConfig.Dimension;
import com.aiep.aihub.domain.hr.HrHardConditionEvaluator.Type;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.HashSet;
import java.util.Set;

/** 发布时完整校验机器可执行标准，草稿保存允许不完整但启用不得缺项。 */
final class HrPositionValidation {
  private HrPositionValidation() {}

  static void validate(Draft draft) {
    if (draft.scoring() == null || draft.hardConditions().isEmpty())
      throw HrPositionService.invalid("至少配置一条硬性条件及评分标准");
    if (draft.scoring().requirements().size() > 100 || draft.criteria().size() > 60)
      throw HrPositionService.invalid("要求数量超过单任务范围");
    if (draft.scoring().requirements().stream().noneMatch(r -> r.dimension() == Dimension.SKILL))
      throw HrPositionService.invalid("至少配置一项核心技能");
    Set<String> ruleIds = new HashSet<>();
    Set<String> ruleTypes = new HashSet<>();
    for (HardRule rule : draft.hardConditions()) {
      HrProtectedAttributes.validateRule(
          rule.label(), rule.expected(), rule.unit(), String.valueOf(rule.values()));
      if (rule.id() == null || !ruleIds.add(rule.id()) || !ruleTypes.add(rule.type()))
        throw HrPositionService.invalid("硬性条件重复");
      Type type;
      try {
        type = Type.valueOf(rule.type());
      } catch (RuntimeException error) {
        throw HrPositionService.invalid("硬性条件类型无效");
      }
      if (rule.label() == null || rule.label().isBlank()) throw HrPositionService.invalid("条件缺少名称");
      if (type == Type.PROJECT_SCALE
          && (rule.values() == null
              || rule.values().size() != 1
              || rule.unit() == null
              || rule.unit().isBlank())) throw HrPositionService.invalid("项目规模条件须配置唯一指标和单位");
      if (type == Type.LANGUAGE && (rule.unit() == null || rule.unit().isBlank()))
        throw HrPositionService.invalid("语言等级须声明同一考试体系，禁止跨体系推测换算");
      if (type == Type.LANGUAGE) {
        if (!HrMatchingService.languageLevelsValid(rule))
          throw HrPositionService.invalid("语言目标等级序号须为正整数，容差须为非负整数且不超过目标序号的30%向下取整");
        var anchor =
            draft.criteria().stream()
                .filter(c -> rule.id().equals(c.id()))
                .findFirst()
                .orElse(null);
        if (!HrMatchingService.languageAnchors(rule, anchor))
          throw HrPositionService.invalid("语言条件须配置明确同体系等级及完整四档锚点");
        if (rule.tolerance() != null
            && rule.tolerance().signum() > 0
            && !anchor.partialAnchor().contains("容差"))
          throw HrPositionService.invalid("语言部分匹配锚点须明确配置容差档，不得泛指不足");
      }
      if (type == Type.REQUIRED_SKILL
          || type == Type.CERTIFICATE
          || type == Type.LOCATION
          || type == Type.LANGUAGE) {
        if (rule.values() == null
            || rule.values().isEmpty()
            || !Set.of("ALL", "ANY").contains(rule.matchMode()))
          throw HrPositionService.invalid("条件缺少标准值或匹配方式");
        if (type == Type.LANGUAGE && rule.tolerance() != null && rule.tolerance().signum() < 0)
          throw HrPositionService.invalid("语言容差不能为负，须在部分匹配锚点明确容差档");
        if (type != Type.LANGUAGE && rule.tolerance() != null && rule.tolerance().signum() != 0)
          throw HrPositionService.invalid("此条件不能设置容差");
      } else {
        if (rule.threshold() == null || rule.threshold().signum() <= 0)
          throw HrPositionService.invalid("条件阈值必须为正");
        BigDecimal max =
            type == Type.EDUCATION
                ? BigDecimal.ONE
                : rule.threshold().multiply(new BigDecimal("0.30")).setScale(0, RoundingMode.FLOOR);
        if (rule.tolerance() != null
            && (rule.tolerance().signum() < 0 || rule.tolerance().compareTo(max) > 0))
          throw HrPositionService.invalid("容差超过允许范围");
      }
    }
    Set<String> ids = new HashSet<>();
    Set<String> coreSkills = new HashSet<>(), bonusSkills = new HashSet<>();
    for (SemanticCriterion c : draft.criteria()) {
      HrProtectedAttributes.validateRule(
          c.label(),
          c.criterion(),
          c.strongAnchor(),
          c.matchAnchor(),
          c.partialAnchor(),
          c.notMetAnchor());
      HrDeterministicAssessments.validate(c);
      String normalized =
          java.text.Normalizer.normalize(
                  c.label() == null ? "" : c.label(), java.text.Normalizer.Form.NFKC)
              .strip()
              .toLowerCase(java.util.Locale.ROOT);
      if ("SKILL".equals(c.dimension()) && !coreSkills.add(normalized))
        throw HrPositionService.invalid("核心技能标准重复");
      if ("BONUS".equals(c.dimension())) bonusSkills.add(normalized);
      if (c.id() == null || !ids.add(c.id())) throw HrPositionService.invalid("语义要求ID重复");
      for (String value :
          new String[] {
            c.label(),
            c.criterion(),
            c.strongAnchor(),
            c.matchAnchor(),
            c.partialAnchor(),
            c.notMetAnchor()
          })
        if (value == null || value.isBlank()) throw HrPositionService.invalid("语义要求必须定义完整评分锚点");
      if (draft.scoring().requirements().stream()
          .anyMatch(r -> r.id().equals(c.id()) && !r.dimension().name().equals(c.dimension())))
        throw HrPositionService.invalid("评分标准与维度不一致");
      if (draft.scoring().requirements().stream().noneMatch(r -> r.id().equals(c.id()))
          && !ruleIds.contains(c.id())) throw HrPositionService.invalid("语义要求未绑定规则");
    }
    for (var requirement : draft.scoring().requirements()) {
      if (requirement.applicable() && !ids.contains(requirement.id()))
        throw HrPositionService.invalid("每项评分要求必须配置证据和评分锚点");
    }
    if (coreSkills.size() > 30 || coreSkills.stream().anyMatch(bonusSkills::contains))
      throw HrPositionService.invalid("核心技能最多30项且不可与加分重复");
    for (var dimension :
        java.util.List.of(Dimension.EXPERIENCE, Dimension.PROJECT, Dimension.EDUCATION)) {
      var selected =
          draft.scoring().requirements().stream()
              .filter(r -> r.applicable() && r.dimension() == dimension)
              .toList();
      if (!selected.isEmpty()
          && selected.stream()
                  .map(r -> r.weight())
                  .reduce(BigDecimal.ZERO, BigDecimal::add)
                  .compareTo(BigDecimal.valueOf(100))
              != 0) throw HrPositionService.invalid("经验、项目、学历维内子项权重须合计100");
    }
    if (draft.scoring().requirements().stream()
        .filter(r -> r.dimension() == Dimension.SKILL)
        .anyMatch(
            r ->
                r.weight().compareTo(BigDecimal.ONE) < 0
                    || r.weight().compareTo(BigDecimal.TEN) > 0))
      throw HrPositionService.invalid("核心技能重要度须为1至10");
    int semanticAtoms = HrTrialEvaluator.plan(draft).requirements().size();
    if (semanticAtoms > 60) throw HrPositionService.invalid("硬软合计语义原子超过60项");
  }
}

package com.aiep.aihub.api.hr;

import com.aiep.aihub.api.hr.HrPositionContracts.*;
import com.aiep.aihub.domain.hr.HrFrozenConfig.Requirement;
import java.util.*;

/** 模板仅包含规则起点，不保存JD、简历及匹配结果。 */
public final class HrTemplateContracts {
  private HrTemplateContracts() {}

  public record Template(
      String id,
      String departmentId,
      String name,
      String family,
      boolean system,
      String status,
      Map<String, Integer> weights,
      List<HardRule> hardConditions,
      List<SemanticCriterion> criteria,
      long version,
      String sourceTemplateId,
      Long sourceVersion,
      List<Requirement> requirements,
      Verification verification,
      Long dictionaryVersion) {
    public Template(
        String id,
        String departmentId,
        String name,
        String family,
        boolean system,
        String status,
        Map<String, Integer> weights,
        List<HardRule> hardConditions,
        List<SemanticCriterion> criteria,
        long version,
        String sourceTemplateId,
        Long sourceVersion,
        List<Requirement> requirements,
        Verification verification) {
      this(
          id,
          departmentId,
          name,
          family,
          system,
          status,
          weights,
          hardConditions,
          criteria,
          version,
          sourceTemplateId,
          sourceVersion,
          requirements,
          verification,
          null);
    }

    public Template(
        String id,
        String departmentId,
        String name,
        String family,
        boolean system,
        String status,
        Map<String, Integer> weights,
        List<HardRule> hardConditions,
        List<SemanticCriterion> criteria,
        long version,
        String sourceTemplateId,
        Long sourceVersion,
        List<Requirement> requirements) {
      this(
          id,
          departmentId,
          name,
          family,
          system,
          status,
          weights,
          hardConditions,
          criteria,
          version,
          sourceTemplateId,
          sourceVersion,
          requirements,
          null,
          null);
    }

    public Template(
        String id,
        String departmentId,
        String name,
        String family,
        boolean system,
        String status,
        Map<String, Integer> weights,
        List<HardRule> hardConditions,
        List<SemanticCriterion> criteria,
        long version,
        String sourceTemplateId,
        Long sourceVersion) {
      this(
          id,
          departmentId,
          name,
          family,
          system,
          status,
          weights,
          hardConditions,
          criteria,
          version,
          sourceTemplateId,
          sourceVersion,
          List.of(),
          null,
          null);
    }

    public Template {
      requirements = requirements == null ? List.of() : List.copyOf(requirements);
      weights = Map.copyOf(weights);
      hardConditions = List.copyOf(hardConditions);
      criteria = List.copyOf(criteria);
    }
  }

  public record Create(
      String departmentId,
      String name,
      String family,
      Map<String, Integer> weights,
      List<HardRule> hardConditions,
      List<SemanticCriterion> criteria,
      List<Requirement> requirements) {
    public Create(
        String departmentId,
        String name,
        String family,
        Map<String, Integer> weights,
        List<HardRule> hardConditions,
        List<SemanticCriterion> criteria) {
      this(departmentId, name, family, weights, hardConditions, criteria, List.of());
    }
  }

  public record Edit(
      long expectedVersion,
      String name,
      Map<String, Integer> weights,
      List<HardRule> hardConditions,
      List<SemanticCriterion> criteria,
      List<Requirement> requirements) {
    public Edit(
        long expectedVersion,
        String name,
        Map<String, Integer> weights,
        List<HardRule> hardConditions,
        List<SemanticCriterion> criteria) {
      this(expectedVersion, name, weights, hardConditions, criteria, List.of());
    }
  }

  public record Copy(String departmentId, String name) {}

  public record Verification(
      String trialId,
      int sampleSize,
      java.math.BigDecimal agreement,
      java.time.Instant verifiedAt,
      String ruleHash) {}

  public record Validate(long expectedVersion, String trialId) {}

  public record SavePosition(
      String positionId, String departmentId, String name, long expectedVersion) {}

  public record CreateFromTemplate(String departmentId, String name, String level, String code) {}
}

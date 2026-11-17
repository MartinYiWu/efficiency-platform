package com.aiep.aihub.api.hr;

import com.aiep.aihub.domain.hr.HrFrozenConfig;
import java.time.Instant;
import java.util.List;

/** 岗位及不可变评分配置的对外合同；版本是并发比较值，不接受客户端指定所有者。 */
public final class HrPositionContracts {
  private HrPositionContracts() {}

  /** 新岗位基础信息；code为空时由服务端生成，family创建后不变。 */
  public record CreatePosition(
      String name, String family, String departmentId, String level, String code) {}

  /** 岗位查询投影；不暴露数据库持久化对象。 */
  public record Position(
      String id,
      String tenantId,
      String name,
      String family,
      String departmentId,
      String level,
      String code,
      String status,
      String configVersion,
      String contextVersion,
      String createdBy,
      Instant createdAt,
      long version) {}

  /** 草稿只作为编排输入，发布时仍需完整服务端校验。 */
  public record Draft(
      String positionId,
      String name,
      String family,
      String departmentId,
      String level,
      String jdText,
      String lastStep,
      HrFrozenConfig scoring,
      List<HardRule> hardConditions,
      List<SemanticCriterion> criteria,
      long version,
      DraftScoring draftScoring,
      List<String> visibleMarks) {
    public Draft(
        String positionId,
        String name,
        String family,
        String departmentId,
        String level,
        String jdText,
        String lastStep,
        HrFrozenConfig scoring,
        List<HardRule> hardConditions,
        List<SemanticCriterion> criteria,
        long version,
        DraftScoring draftScoring) {
      this(
          positionId,
          name,
          family,
          departmentId,
          level,
          jdText,
          lastStep,
          scoring,
          hardConditions,
          criteria,
          version,
          draftScoring,
          null);
    }

    public Draft(
        String positionId,
        String name,
        String family,
        String departmentId,
        String level,
        String jdText,
        String lastStep,
        HrFrozenConfig scoring,
        List<HardRule> hardConditions,
        List<SemanticCriterion> criteria,
        long version) {
      this(
          positionId,
          name,
          family,
          departmentId,
          level,
          jdText,
          lastStep,
          scoring,
          hardConditions,
          criteria,
          version,
          null);
    }

    public Draft {
      hardConditions = hardConditions == null ? List.of() : List.copyOf(hardConditions);
      criteria = criteria == null ? List.of() : List.copyOf(criteria);
      var all =
          java.util.Set.of(
              "MANUAL_REVIEW", "BORDERLINE", "QUALITY_WARNING", "DUPLICATE", "SPECIAL_BACKGROUND");
      visibleMarks =
          visibleMarks == null
              ? List.of(
                  "MANUAL_REVIEW",
                  "BORDERLINE",
                  "QUALITY_WARNING",
                  "DUPLICATE",
                  "SPECIAL_BACKGROUND")
              : List.copyOf(visibleMarks);
      if (!all.containsAll(visibleMarks)
          || new java.util.HashSet<>(visibleMarks).size() != visibleMarks.size())
        throw new IllegalArgumentException("HR_MARK_CONFIGURATION_INVALID");
    }
    /** 发布/停用等聚合事件更新并发版本，但不覆盖保存过的草稿内容。 */
    public Draft atVersion(long currentVersion){return new Draft(positionId,name,family,departmentId,level,jdText,lastStep,scoring,hardConditions,criteria,currentVersion,draftScoring,visibleMarks);}
  }

  /** 编辑中的计分配置允许未完成；发布时freeze执行完整领域不变量，不能直接用于评分。 */
  public record DraftScoring(
      String version,
      java.util.Map<HrFrozenConfig.Dimension, Integer> weights,
      List<HrFrozenConfig.Requirement> requirements,
      Integer highThreshold,
      Integer middleThreshold,
      Integer lowThreshold,
      java.math.BigDecimal minimumCoverage,
      java.math.BigDecimal strongCoverage) {
    public HrFrozenConfig freeze() {
      if (weights == null
          || requirements == null
          || highThreshold == null
          || middleThreshold == null
          || lowThreshold == null
          || minimumCoverage == null
          || strongCoverage == null) throw new IllegalArgumentException("HR_CONFIG_INCOMPLETE");
      return new HrFrozenConfig(
          version == null ? "draft" : version,
          weights,
          requirements,
          highThreshold,
          middleThreshold,
          lowThreshold,
          minimumCoverage,
          strongCoverage);
    }
  }

  /** 阈值与容差使用声明单位，禁止把关键词命中当作能力证据。 */
  public record HardRule(
      String id,
      String type,
      String label,
      String expected,
      String unit,
      java.math.BigDecimal threshold,
      java.math.BigDecimal tolerance,
      boolean overridable,
      List<String> values,
      String matchMode) {}

  /** 语义要求保存可审核的分档锚点，模型不拥有总分和分档。 */
  public record SemanticCriterion(
      String id,
      String label,
      String dimension,
      String criterion,
      String strongAnchor,
      String matchAnchor,
      String partialAnchor,
      String notMetAnchor,
      boolean critical,
      Calculation calculation) {
    public SemanticCriterion(
        String id,
        String label,
        String dimension,
        String criterion,
        String strongAnchor,
        String matchAnchor,
        String partialAnchor,
        String notMetAnchor,
        boolean critical) {
      this(
          id,
          label,
          dimension,
          criterion,
          strongAnchor,
          matchAnchor,
          partialAnchor,
          notMetAnchor,
          critical,
          null);
    }
  }

  /** 确定性子规则；数值以声明单位冻结，空值表示该项仍由证据锚点评估。 */
  public record Calculation(
      String type,
      java.math.BigDecimal minimum,
      java.math.BigDecimal maximum,
      java.math.BigDecimal expected,
      String metric,
      String unit) {}

  /** 发布结果保存配置值和哈希，不会随着岗位后续编辑变化。 */
  public record ContextSnapshot(
      String positionId,
      String name,
      String departmentId,
      String level,
      String jdText,
      String version) {}

  public record ConfigVersion(
      String id,
      String positionId,
      String version,
      String contextVersion,
      Draft snapshot,
      String snapshotHash,
      String publishedBy,
      Instant publishedAt,
      Long dictionaryVersion,
      java.util.Map<String, AssetBinding> bindings,
      ContextSnapshot context) {
    public ConfigVersion(
        String id,
        String positionId,
        String version,
        String contextVersion,
        Draft snapshot,
        String snapshotHash,
        String publishedBy,
        Instant publishedAt,
        Long dictionaryVersion,
        java.util.Map<String, AssetBinding> bindings) {
      this(
          id,
          positionId,
          version,
          contextVersion,
          snapshot,
          snapshotHash,
          publishedBy,
          publishedAt,
          dictionaryVersion,
          bindings,
          null);
    }

    public ConfigVersion(
        String id,
        String positionId,
        String version,
        String contextVersion,
        Draft snapshot,
        String snapshotHash,
        String publishedBy,
        Instant publishedAt) {
      this(
          id,
          positionId,
          version,
          contextVersion,
          snapshot,
          snapshotHash,
          publishedBy,
          publishedAt,
          null,
          java.util.Map.of());
    }

    public ConfigVersion {
      bindings = bindings == null ? java.util.Map.of() : java.util.Map.copyOf(bindings);
    }
  }

  /** 固定已发布资产，仅保存版本与hash，不保存Prompt正文或凭据。 */
  @com.fasterxml.jackson.databind.annotation.JsonNaming(
      com.fasterxml.jackson.databind.PropertyNamingStrategies.SnakeCaseStrategy.class)
  public record AssetBinding(
      String promptVersion,
      String promptHash,
      String modelRouteVersion,
      String modelRoute,
      String outputSchemaHash) {}

  /** 显式版本比较，防止并发编辑覆盖其他招聘人员。 */
  public record Publish(long expectedVersion) {}

  /** 所有列表使用同一分页单位，total仅统计有权限对象。 */
  public record Page<T>(List<T> items, int page, int pageSize, long total) {}
}

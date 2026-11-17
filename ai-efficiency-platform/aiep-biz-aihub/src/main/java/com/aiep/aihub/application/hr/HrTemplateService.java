package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrPositionContracts.*;
import com.aiep.aihub.api.hr.HrTemplateContracts.*;
import com.aiep.aihub.domain.hr.HrFrozenConfig;
import com.aiep.aihub.repository.hr.HrSettingsRepository;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 平台九族不可修改；组织发布追加版本，引用历史不回溯。 */
@Service
public class HrTemplateService {
  private final HrSettingsRepository repository;
  private final HrPositionService positions;
  private HrTrialService trials;

  @org.springframework.beans.factory.annotation.Autowired
  public HrTemplateService(
      HrSettingsRepository repository, HrPositionService positions, HrTrialService trials) {
    this(repository, positions);
    this.trials = trials;
  }

  public HrTemplateService(HrSettingsRepository repository, HrPositionService positions) {
    this.repository = repository;
    this.positions = positions;
  }

  public static List<Template> platformTemplates() {
    String[] families = {
      "TECHNOLOGY",
      "PRODUCT",
      "DESIGN",
      "OPERATIONS",
      "MARKETING",
      "SALES",
      "SUPPORT",
      "MANAGEMENT",
      "GRADUATE"
    };
    String[] names = {"技术研发", "产品", "设计", "运营", "市场", "销售", "职能支持", "管理岗", "应届生"};
    int[][] weights = {
      {40, 25, 25, 5, 5},
      {20, 30, 40, 5, 5},
      {30, 20, 45, 5, 0},
      {25, 30, 35, 5, 5},
      {20, 35, 35, 5, 5},
      {15, 40, 35, 5, 5},
      {30, 35, 20, 10, 5},
      {20, 40, 30, 5, 5},
      {25, 5, 35, 30, 5}
    };
    List<Template> result = new ArrayList<>();
    String[] dimensions = {"SKILL", "EXPERIENCE", "PROJECT", "EDUCATION", "BONUS"};
    for (int i = 0; i < families.length; i++) {
      Map<String, Integer> values = new LinkedHashMap<>();
      for (int j = 0; j < 5; j++) values.put(dimensions[j], weights[i][j]);
      result.add(
          new Template(
              "platform-" + families[i],
              null,
              names[i],
              families[i],
              true,
              "PUBLISHED",
              values,
              List.of(),
              List.of(),
              1,
              null,
              null));
    }
    return List.copyOf(result);
  }

  public List<Template> list(HrActor actor, String department, String family) {
    HrAccessPolicy.require(actor, "hr:config:read");
    if (department != null) HrAccessPolicy.department(actor, department);
    List<Template> all = new ArrayList<>(platformTemplates());
    all.addAll(repository.list(actor, "TEMPLATE", Template.class));
    return all.stream()
        .filter(t -> department == null || t.system() || department.equals(t.departmentId()))
        .filter(t -> family == null || family.isBlank() || family.equals(t.family()))
        .toList();
  }

  public Template get(HrActor actor, String id) {
    HrAccessPolicy.require(actor, "hr:config:read");
    return platformTemplates().stream()
        .filter(t -> t.id().equals(id))
        .findFirst()
        .orElseGet(() -> repository.get(actor, "TEMPLATE", id, Template.class));
  }

  @Transactional
  public Template create(HrActor actor, Create input) {
    HrAccessPolicy.require(actor, "hr:config:edit");
    HrAccessPolicy.requireFor(actor, "hr:config:edit", input.departmentId(), null, "CONFIG");
    if (platformTemplates().stream().noneMatch(t -> t.family().equals(input.family())))
      throw HrPositionService.invalid("岗位族无效");
    var result =
        new Template(
            UUID.randomUUID().toString(),
            input.departmentId(),
            HrPositionService.text(input.name(), 80),
            input.family(),
            false,
            "DRAFT",
            input.weights(),
            input.hardConditions() == null ? List.of() : input.hardConditions(),
            input.criteria() == null ? List.of() : input.criteria(),
            1,
            null,
            null,
            input.requirements());
    validate(result);
    repository.save(actor, "TEMPLATE", result.id(), result.departmentId(), 0, 1, result, "CREATE");
    return result;
  }

  @Transactional
  public Template edit(HrActor actor, String id, Edit input) {
    HrAccessPolicy.require(actor, "hr:config:edit");
    var old = get(actor, id);
    editable(old, input.expectedVersion());
    var next =
        new Template(
            id,
            old.departmentId(),
            HrPositionService.text(input.name(), 80),
            old.family(),
            false,
            "DRAFT",
            input.weights(),
            input.hardConditions() == null ? List.of() : input.hardConditions(),
            input.criteria() == null ? List.of() : input.criteria(),
            old.version() + 1,
            old.sourceTemplateId(),
            old.sourceVersion(),
            input.requirements(),
            null,
            old.dictionaryVersion());
    validate(next);
    repository.save(
        actor,
        "TEMPLATE",
        id,
        next.departmentId(),
        old.version(),
        next.version(),
        next,
        "SAVE_DRAFT");
    return next;
  }

  @Transactional
  public Template publish(HrActor actor, String id, long expected) {
    HrAccessPolicy.require(actor, "hr:config:publish");
    var old = get(actor, id);
    editable(old, expected);
    validate(old);
    var next =
        new Template(
            id,
            old.departmentId(),
            old.name(),
            old.family(),
            false,
            "PUBLISHED",
            old.weights(),
            old.hardConditions(),
            old.criteria(),
            old.version() + 1,
            old.sourceTemplateId(),
            old.sourceVersion(),
            old.requirements(),
            old.verification(),
            old.dictionaryVersion());
    repository.save(
        actor, "TEMPLATE", id, next.departmentId(), old.version(), next.version(), next, "PUBLISH");
    return next;
  }

  @Transactional
  public Template copy(HrActor actor, String id, Copy input) {
    HrAccessPolicy.require(actor, "hr:config:edit");
    var old = get(actor, id);
    HrAccessPolicy.department(actor, input.departmentId());
    var next =
        new Template(
            UUID.randomUUID().toString(),
            input.departmentId(),
            HrPositionService.text(input.name(), 80),
            old.family(),
            false,
            "DRAFT",
            old.weights(),
            old.hardConditions(),
            old.criteria(),
            1,
            id,
            old.version(),
            old.requirements(),
            null,
            old.dictionaryVersion());
    repository.save(actor, "TEMPLATE", next.id(), next.departmentId(), 0, 1, next, "COPY");
    return next;
  }

  @Transactional
  public Position position(HrActor actor, String id, CreateFromTemplate input) {
    var template = get(actor, id);
    HrAccessPolicy.require(actor, "hr:position:edit");
    Position p =
        positions.create(
            actor,
            new CreatePosition(
                input.name(),
                template.family(),
                input.departmentId(),
                input.level(),
                input.code()));
    var weights = new EnumMap<HrFrozenConfig.Dimension, Integer>(HrFrozenConfig.Dimension.class);
    template
        .weights()
        .forEach((key, value) -> weights.put(HrFrozenConfig.Dimension.valueOf(key), value));
    var scoring =
        new DraftScoring(
            "draft",
            weights,
            template.requirements().stream()
                .filter(r -> r.dimension() != HrFrozenConfig.Dimension.SKILL)
                .toList(),
            80,
            65,
            50,
            new java.math.BigDecimal("80"),
            new java.math.BigDecimal("90"));
    positions.save(
        actor,
        p.id(),
        new Draft(
            p.id(),
            p.name(),
            p.family(),
            p.departmentId(),
            p.level(),
            "",
            "HARD_CONDITIONS",
            null,
            template.hardConditions(),
            template.criteria().stream().filter(c -> !"SKILL".equals(c.dimension())).toList(),
            p.version(),
            scoring));
    return positions.get(actor, p.id());
  }

  @Transactional
  public Template fromPosition(HrActor actor, SavePosition input) {
    HrAccessPolicy.requireFor(actor, "hr:config:edit", input.departmentId(), null, "CONFIG");
    var position = positions.get(actor, input.positionId());
    if (position.version() != input.expectedVersion()) throw HrPositionService.conflict();
    if (position.configVersion() == null) throw HrPositionService.invalid("只有已发布岗位可另存模板");
    var config = positions.config(actor, position.id(), position.configVersion());
    var draft = config.snapshot();
    Map<String, Integer> weights = new LinkedHashMap<>();
    draft.scoring().weights().forEach((key, value) -> weights.put(key.name(), value));
    var created =
        create(
            actor,
            new Create(
                input.departmentId(),
                input.name(),
                position.family(),
                weights,
                draft.hardConditions(),
                draft.criteria(),
                draft.scoring().requirements()));
    var frozen =
        new Template(
            created.id(),
            created.departmentId(),
            created.name(),
            created.family(),
            false,
            created.status(),
            created.weights(),
            created.hardConditions(),
            created.criteria(),
            created.version() + 1,
            created.sourceTemplateId(),
            created.sourceVersion(),
            created.requirements(),
            null,
            config.dictionaryVersion());
    repository.save(
        actor,
        "TEMPLATE",
        created.id(),
        created.departmentId(),
        created.version(),
        frozen.version(),
        frozen,
        "FREEZE_DICTIONARY");
    return frozen;
  }

  @Transactional
  public Template validateTrial(HrActor actor, String id, Validate input) {
    HrAccessPolicy.require(actor, "hr:config:publish");
    var old = get(actor, id);
    editable(old, input.expectedVersion());
    var trial = trials.get(actor, input.trialId());
    if (!old.departmentId().equals(trial.departmentId())
        || !trial.verified()
        || trial.agreement() == null
        || trial.actualSize() < 10) throw HrPositionService.invalid("须同部门至少10份独立标注且一致率≥85%的预演");
    var d = trial.frozenDraft();
    Map<String, Integer> weights = new LinkedHashMap<>();
    d.scoring().weights().forEach((key, value) -> weights.put(key.name(), value));
    String templateHash =
        ruleHash(
            old.family(), old.weights(), old.hardConditions(), old.criteria(), old.requirements());
    String trialHash =
        ruleHash(d.family(), weights, d.hardConditions(), d.criteria(), d.scoring().requirements());
    if (!templateHash.equals(trialHash))
      throw new HrBusinessException("HR_TEMPLATE_TRIAL_MISMATCH", "预演规则与模板不一致，不能标记已验证", 409);
    var verification =
        new Verification(
            trial.id(),
            trial.actualSize(),
            trial.agreement(),
            java.time.Instant.now(),
            templateHash);
    var next =
        new Template(
            old.id(),
            old.departmentId(),
            old.name(),
            old.family(),
            false,
            old.status(),
            old.weights(),
            old.hardConditions(),
            old.criteria(),
            old.version() + 1,
            old.sourceTemplateId(),
            old.sourceVersion(),
            old.requirements(),
            verification,
            trial.dictionaryVersion());
    repository.save(
        actor,
        "TEMPLATE",
        id,
        old.departmentId(),
        old.version(),
        next.version(),
        next,
        "VALIDATE_TRIAL");
    return next;
  }

  private static String ruleHash(
      String family, Object weights, Object hard, Object criteria, Object requirements) {
    return HrPositionService.hash(List.of(family, weights, hard, criteria, requirements));
  }

  public List<Template> versions(HrActor actor, String id) {
    var t = get(actor, id);
    return t.system() ? List.of(t) : repository.versions(actor, "TEMPLATE", id, Template.class);
  }

  private static void editable(Template t, long expected) {
    if (t.system())
      throw new HrBusinessException("HR_PLATFORM_TEMPLATE_IMMUTABLE", "平台模板仅可复制", 403);
    if (t.version() != expected) throw HrPositionService.conflict();
  }

  private static void validate(Template t) {
    var dims = Set.of("SKILL", "EXPERIENCE", "PROJECT", "EDUCATION", "BONUS");
    if (!t.weights().keySet().equals(dims)
        || t.weights().values().stream().anyMatch(v -> v < 0 || v > 100)
        || t.weights().values().stream().mapToInt(Integer::intValue).sum() != 100)
      throw HrPositionService.invalid("模板五维权重必须合计100");
    if (t.hardConditions().size() + t.criteria().size() > 100)
      throw HrPositionService.invalid("模板要求超过上限");
    if (t.requirements().stream().map(HrFrozenConfig.Requirement::id).distinct().count()
        != t.requirements().size()) throw HrPositionService.invalid("模板要求ID重复");
    for (var r : t.requirements())
      if (t.criteria().stream()
          .noneMatch(c -> c.id().equals(r.id()) && c.dimension().equals(r.dimension().name())))
        throw HrPositionService.invalid("模板评分项缺少对应标准");
    String text = t.hardConditions().toString() + t.criteria().toString();
    HrProtectedAttributes.validateRule(text);
    for (String prohibited : HrSettingsService.defaults(t.departmentId()).prohibitedAttributes())
      if (text.contains(prohibited)) throw HrPositionService.invalid("模板含禁用属性");
  }
}

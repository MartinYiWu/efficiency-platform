package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.api.hr.HrPositionContracts.*;
import com.aiep.aihub.repository.hr.HrPositionRepository;
import com.fasterxml.jackson.core.JsonProcessingException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.text.Normalizer;
import java.time.Clock;
import java.util.HexFormat;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class HrPositionService {
  private static final Set<String> FAMILIES =
      Set.of(
          "TECHNOLOGY",
          "PRODUCT",
          "DESIGN",
          "OPERATIONS",
          "MARKETING",
          "SALES",
          "SUPPORT",
          "MANAGEMENT",
          "GRADUATE");
  private final HrPositionRepository repository;
  private final Clock clock;
  private HrContextService contexts;
  private HrReadinessService readiness;
  private HrPublishedBindingService bindings;
  private org.springframework.transaction.support.TransactionTemplate transactions;

  public HrPositionService(HrPositionRepository repository) {
    this(repository, Clock.systemUTC());
  }

  public HrPositionService(HrPositionRepository repository, HrContextService contexts) {
    this(repository);
    this.contexts = contexts;
  }

  @Autowired
  public HrPositionService(
      HrPositionRepository repository,
      HrContextService contexts,
      HrReadinessService readiness,
      HrPublishedBindingService bindings,
      org.springframework.transaction.PlatformTransactionManager manager) {
    this(repository, contexts);
    this.readiness = readiness;
    this.bindings = bindings;
    this.transactions = new org.springframework.transaction.support.TransactionTemplate(manager);
  }

  public HrPositionService(HrPositionRepository repository, Clock clock) {
    this.repository = repository;
    this.clock = clock;
  }

  @Transactional
  public Position create(HrActor actor, CreatePosition request) {
    HrAccessPolicy.require(actor, "hr:position:edit");
    HrAccessPolicy.department(actor, request.departmentId());
    HrAccessPolicy.requireFor(actor, "hr:position:edit", request.departmentId(), null, "POSITION");
    if (!FAMILIES.contains(request.family())) throw invalid("岗位族无效");
    String name = text(request.name(), 80);
    String level = text(request.level(), 32);
    String id = UUID.randomUUID().toString();
    String code =
        request.code() == null || request.code().isBlank()
            ? code(actor, request.departmentId())
            : text(request.code(), 64);
    Position position =
        new Position(
            id,
            actor.tenantId(),
            name,
            request.family(),
            request.departmentId(),
            level,
            code,
            "DRAFT",
            null,
            "ctx-1",
            actor.userId(),
            clock.instant(),
            1);
    try {
      repository.insert(position);
    } catch (DuplicateKeyException error) {
      throw new HrBusinessException("HR_POSITION_DUPLICATE", "该部门已存在同名岗位或编码", 409);
    }
    return position;
  }

  public Position get(HrActor actor, String id) {
    HrAccessPolicy.require(actor, "hr:position:read");
    Position position = repository.find(actor.tenantId(), id);
    if (position == null) throw missing();
    HrAccessPolicy.department(actor, position.departmentId());
    HrAccessPolicy.position(actor, id);
    HrAccessPolicy.requireFor(actor, "hr:position:read", position.departmentId(), id, "POSITION");
    return position;
  }

  public Page<Position> list(HrActor actor, String keyword, int page, int pageSize) {
    return list(actor, keyword, null, null, page, pageSize);
  }

  public Page<Position> list(
      HrActor actor, String keyword, String family, String status, int page, int pageSize) {
    HrAccessPolicy.require(actor, "hr:position:read");
    if (page < 1 || pageSize < 1 || pageSize > 100) throw invalid("分页参数无效");
    if (actor.departmentIds().isEmpty()) return new Page<>(List.of(), page, pageSize, 0);
    if (family != null && !family.isBlank() && !FAMILIES.contains(family)) throw invalid("岗位族无效");
    if (status != null
        && !status.isBlank()
        && !Set.of("DRAFT", "ACTIVE", "DISABLED").contains(status)) throw invalid("岗位状态无效");
    return new Page<>(
        repository.listGranted(actor, keyword, family, status, (page - 1) * pageSize, pageSize),
        page,
        pageSize,
        repository.countGranted(actor, keyword, family, status));
  }

  public Draft draft(HrActor actor, String positionId) {
    Position p = get(actor, positionId);
    Draft existing = repository.draft(actor.tenantId(), positionId);
    return existing == null
        ? new Draft(
            p.id(),
            p.name(),
            p.family(),
            p.departmentId(),
            p.level(),
            "",
            "BASIC",
            null,
            List.of(),
            List.of(),
            p.version())
        : existing.atVersion(p.version());
  }

  @Transactional
  public Draft save(HrActor actor, String positionId, Draft draft) {
    HrAccessPolicy.require(actor, "hr:position:edit");
    Position p = get(actor, positionId);
    HrAccessPolicy.requireFor(actor, "hr:position:edit", p.departmentId(), p.id(), "POSITION");
    if (!p.id().equals(draft.positionId())
        || !p.family().equals(draft.family())
        || !p.departmentId().equals(draft.departmentId())) throw invalid("岗位归属或岗位族不可修改");
    if (!Set.of("BASIC", "HARD_CONDITIONS", "SOFT_REQUIREMENTS", "WEIGHTS", "PREVIEW")
        .contains(draft.lastStep())) throw invalid("配置步骤无效");
    if (draft.jdText() != null && draft.jdText().length() > 20_000) throw invalid("JD超过20000字");
    Draft next =
        new Draft(
            positionId,
            text(draft.name(), 80),
            draft.family(),
            draft.departmentId(),
            text(draft.level(), 32),
            draft.jdText(),
            draft.lastStep(),
            draft.scoring(),
            draft.hardConditions(),
            draft.criteria(),
            draft.version() + 1,
            draft.draftScoring(),
            draft.visibleMarks());
    if (!repository.saveDraft(actor.tenantId(), next, draft.version())) throw conflict();
    if (contexts != null) {
      String context = contexts.freeze(actor, next);
      if (!repository.context(
          actor.tenantId(), positionId, context, next.name(), next.level(), next.version()))
        throw conflict();
    }
    return next;
  }

  public List<ConfigVersion> versions(HrActor actor, String position) {
    get(actor, position);
    return repository.configs(actor.tenantId(), position).stream()
        .sorted(java.util.Comparator.comparing(ConfigVersion::publishedAt).reversed())
        .toList();
  }

  public record Change(String field, Object oldValue, Object newValue) {}

  public record Difference(String from, String to, List<Change> changes) {}

  public Difference diff(HrActor actor, String position, String from, String to) {
    var a = config(actor, position, from).snapshot();
    var b = config(actor, position, to).snapshot();
    var changes = new java.util.ArrayList<Change>();
    if (!a.hardConditions().equals(b.hardConditions()))
      changes.add(new Change("hardConditions", a.hardConditions(), b.hardConditions()));
    if (!a.criteria().equals(b.criteria()))
      changes.add(new Change("criteria", a.criteria(), b.criteria()));
    if (!a.scoring().equals(b.scoring()))
      changes.add(new Change("scoring", a.scoring(), b.scoring()));
    return new Difference(from, to, changes);
  }

  public ConfigVersion publish(HrActor actor, String id, long expectedVersion) {
    Position p = get(actor, id);
    HrAccessPolicy.requireFor(actor, "hr:position:publish", p.departmentId(), id, "POSITION");
    Long dictionary =
        bindings == null ? null : bindings.validateDictionary(actor, p.departmentId());
    var assets =
        readiness == null ? java.util.Map.<String, AssetBinding>of() : readiness.bindings(actor);
    return transactions == null
        ? publishFrozen(actor, id, expectedVersion, dictionary, assets)
        : transactions.execute(
            status -> publishFrozen(actor, id, expectedVersion, dictionary, assets));
  }

  private ConfigVersion publishFrozen(
      HrActor actor,
      String id,
      long expectedVersion,
      Long dictionary,
      java.util.Map<String, AssetBinding> assets) {
    HrAccessPolicy.require(actor, "hr:position:publish");
    Position position = get(actor, id);
    HrAccessPolicy.requireFor(
        actor, "hr:position:publish", position.departmentId(), id, "POSITION");
    Draft draft = repository.draft(actor.tenantId(), id);
    if (position.version() != expectedVersion || draft == null) throw conflict();
    draft=draft.atVersion(expectedVersion);
    if (draft.scoring() == null && draft.draftScoring() != null)
      draft =
          new Draft(
              draft.positionId(),
              draft.name(),
              draft.family(),
              draft.departmentId(),
              draft.level(),
              draft.jdText(),
              draft.lastStep(),
              draft.draftScoring().freeze(),
              draft.hardConditions(),
              draft.criteria(),
              draft.version(),
              null,
              draft.visibleMarks());
    HrPositionValidation.validate(draft);
    if (position.configVersion() != null) {
      ConfigVersion previous = repository.config(actor.tenantId(), id, position.configVersion());
      if (previous != null && sameRules(previous.snapshot(), draft)&&java.util.Objects.equals(previous.dictionaryVersion(),dictionary)&&previous.bindings().equals(assets)) {
        if (!repository.activate(
            actor.tenantId(), id, previous.version(), position.contextVersion(), expectedVersion))
          throw conflict();
        return withCurrentContext(actor, position, previous);
      }
    }
    String version =
        position.configVersion() == null
            ? "v1.0"
            : nextVersion(position.configVersion(), hardChanged(actor, position, draft));
    draft = freezeVersion(draft, version);
    String contextVersion =
        contexts == null ? position.contextVersion() : contexts.freeze(actor, draft);
    ConfigVersion config =
        new ConfigVersion(
            UUID.randomUUID().toString(),
            id,
            version,
            contextVersion,
            draft,
            hash(draft),
            actor.userId(),
            clock.instant(),
            dictionary,
            assets,
            contextSnapshot(actor, id, contextVersion, draft));
    repository.insertConfig(actor.tenantId(), config);
    if (!repository.activate(actor.tenantId(), id, version, contextVersion, expectedVersion))
      throw conflict();
    repository.applyPublishedMetadata(actor.tenantId(), config);
    repository.stalePreviousResults(actor.tenantId(), id, version);
    return config;
  }

  @Transactional
  public ConfigVersion publishScoring(
      HrActor actor,
      String id,
      long expectedVersion,
      com.aiep.aihub.domain.hr.HrFrozenConfig scoring) {
    HrAccessPolicy.require(actor, "hr:position:publish");
    Position p = get(actor, id);
    HrAccessPolicy.requireFor(actor, "hr:position:publish", p.departmentId(), id, "POSITION");
    if (p.version() != expectedVersion) throw conflict();
    ConfigVersion original = config(actor, id, p.configVersion());
    Draft old = original.snapshot();
    Draft next =
        new Draft(
            id,
            old.name(),
            old.family(),
            old.departmentId(),
            old.level(),
            old.jdText(),
            "PREVIEW",
            scoring,
            old.hardConditions(),
            old.criteria(),
            expectedVersion,
            null,
            old.visibleMarks());
    HrPositionValidation.validate(next);
    String version = nextVersion(p.configVersion(), false);
    next = freezeVersion(next, version);
    ConfigVersion result =
        new ConfigVersion(
            UUID.randomUUID().toString(),
            id,
            version,
            p.contextVersion(),
            next,
            hash(next),
            actor.userId(),
            clock.instant(),
            original.dictionaryVersion(),
            original.bindings(),
            contextSnapshot(actor, id, p.contextVersion(), old));
    repository.insertConfig(actor.tenantId(), result);
    if (!repository.activate(actor.tenantId(), id, version, p.contextVersion(), expectedVersion))
      throw conflict();
    repository.stalePreviousResults(actor.tenantId(), id, version);
    return result;
  }

  public ConfigVersion withCurrentContext(HrActor actor, Position position, ConfigVersion config) {
    HrAccessPolicy.requireFor(
        actor, "hr:position:read", position.departmentId(), position.id(), "POSITION");
    if (!position.id().equals(config.positionId())) throw missing();
    return new ConfigVersion(
        config.id(),
        config.positionId(),
        config.version(),
        position.contextVersion(),
        config.snapshot(),
        config.snapshotHash(),
        config.publishedBy(),
        config.publishedAt(),
        config.dictionaryVersion(),
        config.bindings(),
        contextSnapshot(actor, position.id(), position.contextVersion(), config.snapshot()));
  }

  private ContextSnapshot contextSnapshot(
      HrActor actor, String position, String version, Draft fallback) {
    if (contexts == null)
      return new ContextSnapshot(
          position,
          fallback.name(),
          fallback.departmentId(),
          fallback.level(),
          fallback.jdText(),
          version);
    var frozen = contexts.get(actor, position, version);
    if (!position.equals(frozen.positionId()) || !version.equals(frozen.version())) throw missing();
    return new ContextSnapshot(
        frozen.positionId(),
        frozen.name(),
        frozen.departmentId(),
        frozen.level(),
        frozen.jdText(),
        frozen.version());
  }

  public ConfigVersion config(HrActor actor, String positionId, String version) {
    get(actor, positionId);
    ConfigVersion config = repository.config(actor.tenantId(), positionId, version);
    if (config == null) throw missing();
    return config;
  }

  @Transactional
  public Position disable(HrActor actor, String id, long expectedVersion) {
    HrAccessPolicy.require(actor, "hr:position:publish");
    Position p = get(actor, id);
    HrAccessPolicy.requireFor(actor, "hr:position:publish", p.departmentId(), id, "POSITION");
    if (!repository.disable(actor.tenantId(), id, expectedVersion)) throw conflict();
    return get(actor, id);
  }

  private boolean hardChanged(HrActor actor, Position position, Draft draft) {
    ConfigVersion old =
        repository.config(actor.tenantId(), position.id(), position.configVersion());
    return old == null || !old.snapshot().hardConditions().equals(draft.hardConditions());
  }

  private static boolean sameRules(Draft a, Draft b) {
    var x = a.scoring();
    var y = b.scoring();
    return a.visibleMarks().equals(b.visibleMarks())
        && a.hardConditions().equals(b.hardConditions())
        && a.criteria().equals(b.criteria())
        && x.weights().equals(y.weights())
        && x.requirements().equals(y.requirements())
        && x.highThreshold() == y.highThreshold()
        && x.middleThreshold() == y.middleThreshold()
        && x.lowThreshold() == y.lowThreshold()
        && x.minimumCoverage().compareTo(y.minimumCoverage()) == 0
        && x.strongCoverage().compareTo(y.strongCoverage()) == 0;
  }

  private static String nextVersion(String current, boolean major) {
    String[] parts = current.substring(1).split("\\.");
    return "v"
        + (Integer.parseInt(parts[0]) + (major ? 1 : 0))
        + "."
        + (major ? 0 : Integer.parseInt(parts[1]) + 1);
  }

  private String code(HrActor actor, String department) {
    long next = repository.nextCode(actor.tenantId(), department);
    if (next > 999999) throw invalid("部门岗位编码已达到上限");
    return department + "-" + String.format(java.util.Locale.ROOT, "%06d", next);
  }

  private static Draft freezeVersion(Draft draft, String version) {
    var s = draft.scoring();
    var next =
        new com.aiep.aihub.domain.hr.HrFrozenConfig(
            version,
            s.weights(),
            s.requirements(),
            s.highThreshold(),
            s.middleThreshold(),
            s.lowThreshold(),
            s.minimumCoverage(),
            s.strongCoverage());
    return new Draft(
        draft.positionId(),
        draft.name(),
        draft.family(),
        draft.departmentId(),
        draft.level(),
        draft.jdText(),
        draft.lastStep(),
        next,
        draft.hardConditions(),
        draft.criteria(),
        draft.version(),
        null,
        draft.visibleMarks());
  }

  static String hash(Object value) {
    try {
      byte[] json =
          com.fasterxml.jackson.databind.json.JsonMapper.builder()
              .enable(com.fasterxml.jackson.databind.MapperFeature.SORT_PROPERTIES_ALPHABETICALLY)
              .enable(com.fasterxml.jackson.databind.SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS)
              .build()
              .findAndRegisterModules()
              .writeValueAsString(value)
              .getBytes(StandardCharsets.UTF_8);
      return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(json));
    } catch (JsonProcessingException | NoSuchAlgorithmException error) {
      throw new IllegalStateException("HR_SNAPSHOT_ENCODING_FAILED");
    }
  }

  static String text(String value, int max) {
    if (value == null) throw invalid("缺少必填字段");
    String normalized = Normalizer.normalize(value, Normalizer.Form.NFKC).strip();
    if (normalized.isBlank() || normalized.codePointCount(0, normalized.length()) > max)
      throw invalid("字段为空或超出长度");
    return normalized;
  }

  static HrBusinessException invalid(String message) {
    return new HrBusinessException("HR_CONFIG_INVALID", message, 422);
  }

  static HrBusinessException missing() {
    return new HrBusinessException("HR_OBJECT_NOT_FOUND", "对象不存在或不可访问", 404);
  }

  static HrBusinessException conflict() {
    return new HrBusinessException("HR_VERSION_CONFLICT", "配置已更新，请重新加载后操作", 409);
  }
}

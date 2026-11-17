package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.api.hr.HrPositionContracts.*;
import com.aiep.aihub.domain.hr.*;
import com.aiep.aihub.domain.hr.HrHardConditionEvaluator.*;
import com.aiep.aihub.repository.hr.HrMatchingRepository;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Service;

@Service
public class HrMatchingService {
  void cancelBatchScope(String tenant, String scope) {
    repository.cancelScope(tenant, scope);
  }

  void confirmBatchScopeCancellation(String tenant, String scope) {
    repository.confirmScopeCancellation(tenant, scope);
  }

  public record Statistics(
      long total,
      long strongRecommend,
      long recommend,
      long review,
      long notRecommend,
      long filtered,
      long reviewRequired) {}

  public Statistics statistics(HrActor actor, String positionId, String version) {
    var p = positions.get(actor, positionId);
    HrAccessPolicy.require(actor, "hr:candidate:read");
    HrAccessPolicy.requireFor(actor, "hr:matching:read", p.departmentId(), p.id(), "POSITION");
    if (version == null || version.isBlank()) throw HrPositionService.invalid("请选择同一评分版本");
    positions.config(actor, p.id(), version);
    long total = 0, strong = 0, recommend = 0, review = 0, low = 0, filtered = 0, required = 0;
    for (var row : repository.statistics(actor, positionId, version)) {
      total += row.count();
      if ("FILTERED".equals(row.businessStatus())) filtered += row.count();
      else if ("REVIEW_REQUIRED".equals(row.businessStatus())) required += row.count();
      else if ("SCORED".equals(row.businessStatus()))
        switch (Objects.toString(row.band(), "")) {
          case "STRONG_RECOMMEND" -> strong += row.count();
          case "RECOMMEND" -> recommend += row.count();
          case "REVIEW" -> review += row.count();
          case "NOT_RECOMMEND" -> low += row.count();
          default -> {}
        }
    }
    return new Statistics(total, strong, recommend, review, low, filtered, required);
  }

  private final HrCandidateService candidates;
  private final HrPositionService positions;
  private final HrMatchingRepository repository;
  private final HrSemanticGateway gateway;
  private final HrResultAssembler assembler;
  private final ObjectMapper json;
  private final HrSensitiveJsonCodec codec;
  private HrActorAuthority authority;
  private HrSourceAuthorization sources;
  private HrMatchingExecutionPlans executionPlans;

  public HrMatchingService(
      HrCandidateService candidates,
      HrPositionService positions,
      HrMatchingRepository repository,
      HrSemanticGateway gateway,
      HrResultAssembler assembler,
      ObjectMapper json,
      HrSensitiveJsonCodec codec,
      HrActorAuthority authority,
      HrSourceAuthorization sources) {
    this(candidates, positions, repository, gateway, assembler, json, codec);
    this.authority = authority;
    this.sources = sources;
  }

  @org.springframework.beans.factory.annotation.Autowired
  public HrMatchingService(
      HrCandidateService candidates,
      HrPositionService positions,
      HrMatchingRepository repository,
      HrSemanticGateway gateway,
      HrResultAssembler assembler,
      ObjectMapper json,
      HrSensitiveJsonCodec codec,
      HrActorAuthority authority,
      HrSourceAuthorization sources,
      HrMatchingExecutionPlans executionPlans) {
    this(candidates, positions, repository, gateway, assembler, json, codec, authority, sources);
    this.executionPlans = executionPlans;
  }

  public HrMatchingService(
      HrCandidateService candidates,
      HrPositionService positions,
      HrMatchingRepository repository,
      HrSemanticGateway gateway,
      HrResultAssembler assembler,
      ObjectMapper json,
      HrSensitiveJsonCodec codec) {
    this.candidates = candidates;
    this.positions = positions;
    this.repository = repository;
    this.gateway = gateway;
    this.assembler = assembler;
    this.json = json;
    this.codec = codec;
  }

  public Matching get(HrActor actor, String id) {
    HrAccessPolicy.require(actor, "hr:matching:read");
    var result = repository.result(actor.tenantId(), id);
    if (result == null) throw HrPositionService.missing();
    candidates.candidate(actor, result.candidateId());
    var position = positions.get(actor, result.positionId());
    HrAccessPolicy.requireFor(
        actor, "hr:matching:read", position.departmentId(), position.id(), "POSITION");
    return assembler.project(
        actor,
        assembler.status(
            read(result.resultJson(), Matching.class), result.status(), result.supersededBy()));
  }

  public ConfigVersion configurationSnapshot(HrActor actor, String resultId) {
    Matching result = get(actor, resultId);
    var semantic = repository.semantic(actor.tenantId(), result.semanticSnapshotId());
    if (semantic == null
        || !semantic.candidateId().equals(result.candidateId())
        || !semantic.factSnapshotId().equals(result.factSnapshotId()))
      throw HrPositionService.missing();
    return read(semantic.configJson(), ConfigVersion.class);
  }

  public Page<Matching> list(
      HrActor actor,
      String positionId,
      String candidateId,
      String configVersionId,
      String businessStatus,
      String keyword,
      int page,
      int pageSize) {
    HrAccessPolicy.require(actor, "hr:matching:read");
    HrAccessPolicy.require(actor, "hr:candidate:read");
    HrAccessPolicy.require(actor, "hr:position:read");
    if (page < 1 || pageSize < 1 || pageSize > 100) throw HrPositionService.invalid("分页参数无效");
    if (positionId != null) positions.get(actor, positionId);
    if (candidateId != null) candidates.candidate(actor, candidateId);
    if (keyword != null && !keyword.isBlank())
      throw HrPositionService.invalid("加密姓名检索尚未配置，请使用岗位或候选人筛选");
    if (businessStatus != null
        && !Set.of("SCORED", "FILTERED", "REVIEW_REQUIRED", "STALE", "SUPERSEDED", "TEMPORARY")
            .contains(businessStatus)) throw HrPositionService.invalid("结果状态无效");
    var rows =
        repository
            .listGranted(
                actor.tenantId(),
                actor.departmentIds(),
                positionId,
                candidateId,
                configVersionId,
                businessStatus,
                actor.positionIds(),
                actor.candidateIds(),
                (page - 1) * pageSize,
                pageSize,
                actor.authenticated() ? actor.grants() : List.of())
            .stream()
            .map(
                r ->
                    assembler.project(
                        actor,
                        assembler.status(
                            read(r.resultJson(), Matching.class), r.status(), r.supersededBy())))
            .toList();
    return new Page<>(
        rows,
        page,
        pageSize,
        repository.countGranted(
            actor.tenantId(),
            actor.departmentIds(),
            positionId,
            candidateId,
            configVersionId,
            businessStatus,
            actor.positionIds(),
            actor.candidateIds(),
            actor.authenticated() ? actor.grants() : List.of()));
  }

  public Run run(HrActor actor, String id) {
    HrAccessPolicy.require(actor, "hr:matching:read");
    Run run = repository.run(actor.tenantId(), id);
    if (run == null) throw HrPositionService.missing();
    candidates.candidate(actor, run.candidateId());
    var position = positions.get(actor, run.positionId());
    HrAccessPolicy.requireFor(
        actor, "hr:matching:read", position.departmentId(), position.id(), "POSITION");
    return run;
  }

  public void authorizeFeedback(HrActor actor, Matching result) {
    var p = positions.get(actor, result.positionId());
    HrAccessPolicy.requireFor(actor, "hr:matching:feedback", p.departmentId(), p.id(), "POSITION");
  }

  public Run prepare(HrActor actor, MatchRequest request, String idempotencyKey) {
    return prepareBound(actor, request, idempotencyKey, null);
  }

  public Run prepareBound(
      HrActor actor, MatchRequest request, String idempotencyKey, String scopeRef) {
    boolean direct = scopeRef == null;
    HrAccessPolicy.require(actor, "hr:matching:run");
    HrAccessPolicy.require(actor, "hr:matching:read");
    var position = positions.get(actor, request.positionId());
    HrAccessPolicy.requireFor(
        actor, "hr:matching:run", position.departmentId(), position.id(), "POSITION");
    HrAccessPolicy.requireFor(
        actor, "hr:matching:read", position.departmentId(), position.id(), "POSITION");
    if (!position.status().equals("ACTIVE")) throw HrPositionService.invalid("岗位尚未启用");
    Snapshot snapshot = candidates.snapshot(actor, request.candidateId());
    if (sources != null)
      sources.requireMatching(
          actor, candidates.candidate(actor, request.candidateId()), request.positionId());
    Facts facts = candidates.decode(snapshot);
    if (facts.version() != request.expectedVersion()) throw HrPositionService.conflict();
    if (idempotencyKey == null || !idempotencyKey.matches("[A-Za-z0-9_-]{8,100}"))
      throw HrPositionService.invalid("缺少有效幂等键");
    String requestHash = HrPositionService.hash(request);
    Run existing = repository.findIdempotency(actor.tenantId(), idempotencyKey);
    if (existing != null) {
      if (!requestHash.equals(existing.requestHash())) throw HrPositionService.conflict();
      return existing;
    }
    var publishedConfig = positions.config(actor, position.id(), position.configVersion());
    var config = positions.withCurrentContext(actor, position, publishedConfig);
    String id = UUID.randomUUID().toString();
    Instant deadline = Instant.now().plusSeconds(600);
    if (direct) {
      LocalDate asOf = LocalDate.now(ZoneId.of("Asia/Shanghai"));
      Instant todayStart = asOf.atStartOfDay(ZoneId.of("Asia/Shanghai")).toInstant();
      for (var previous :
          repository.recentRuns(
              actor.tenantId(), facts.candidateId(), position.id(), todayStart, 100)) {
        JsonNode previousInput;
        try {
          previousInput = json.readTree(codec.open(previous.inputJson()));
        } catch (com.fasterxml.jackson.core.JsonProcessingException invalid) {
          throw new HrBusinessException("HR_RUN_SNAPSHOT_INVALID", "历史匹配输入快照无法验证", 409);
        }
        if (!previousInput.has("factSnapshotId")
            || !previousInput.path("facts").isObject()
            || !previousInput.path("config").isObject()
            || !previousInput.path("position").isObject()) continue;
        if (snapshot.id().equals(previousInput.path("factSnapshotId").asText())
            && facts.candidateId().equals(previousInput.path("facts").path("candidateId").asText())
            && position.id().equals(previousInput.path("position").path("id").asText())
            && config
                .snapshotHash()
                .equals(previousInput.path("config").path("snapshotHash").asText())
            && config
                .contextVersion()
                .equals(previousInput.path("config").path("contextVersion").asText()))
          return previous;
      }
      String signature =
          HrPositionService.hash(
              List.of(config.version(), config.snapshotHash(), config.bindings()));
      scopeRef =
          executionPlans == null
              ? "hr-match-"
                  + UUID.nameUUIDFromBytes(
                      (actor.tenantId()
                              + ":"
                              + snapshot.id()
                              + ":"
                              + position.id()
                              + ":"
                              + signature
                              + ":"
                              + config.contextVersion()
                              + ":"
                              + asOf)
                          .getBytes(java.nio.charset.StandardCharsets.UTF_8))
              : executionPlans.scope(
                  actor,
                  facts.candidateId(),
                  snapshot.id(),
                  position.id(),
                  signature,
                  config.contextVersion(),
                  asOf);
      if (executionPlans != null) {
        Run same = executionPlans.findRun(actor, scopeRef);
        if (same != null) return same;
        int atoms = requirements(config).criteria().size();
        var plan = executionPlans.prepare(actor, id, scopeRef, (atoms + 14) / 15, atoms > 0);
        id = plan.runId();
        deadline = plan.deadline();
        same = executionPlans.findRun(actor, scopeRef);
        if (same != null) return same;
      }
    }
    Run run =
        new Run(
            id,
            actor.tenantId(),
            facts.candidateId(),
            position.id(),
            "PENDING",
            null,
            null,
            Instant.now(),
            write(new FrozenInput(request, facts, snapshot.id(), position, config)),
            deadline,
            idempotencyKey,
            requestHash,
            scopeRef);
    try {
      repository.insertRun(run);
    } catch (org.springframework.dao.DuplicateKeyException error) {
      Run raced =
          direct && executionPlans != null
              ? executionPlans.findRun(actor, scopeRef)
              : repository.findIdempotency(actor.tenantId(), idempotencyKey);
      if (raced == null || !requestHash.equals(raced.requestHash()))
        throw HrPositionService.conflict();
      return raced;
    }
    return run;
  }

  public Run cancel(HrActor actor, String id) {
    HrAccessPolicy.require(actor, "hr:matching:run");
    Run target = run(actor, id);
    var position = positions.get(actor, target.positionId());
    HrAccessPolicy.requireFor(
        actor, "hr:matching:run", position.departmentId(), position.id(), "POSITION");
    repository.cancel(actor.tenantId(), id);
    return run(actor, id);
  }

  public boolean cancelAgent(HrActor actor, String id) {
    Run run = run(actor, id);
    if (!run.status().equals("CANCEL_PENDING")) return run.status().equals("CANCELLED");
    boolean confirmed = gateway.cancel(actor, run.scopeRef());
    repository.confirmCancellation(actor.tenantId(), id, confirmed);
    return confirmed;
  }

  public void failQueued(HrActor actor, String id) {
    if (repository.start(actor.tenantId(), id))
      repository.finishRun(actor.tenantId(), id, "FAILED", null, "HR_EVALUATION_QUEUE_UNAVAILABLE");
  }

  public Matching execute(HrActor originalActor, MatchRequest request, String runId) {
    final HrActor actor = authority == null ? originalActor : authority.refresh(originalActor);
    Run frozen = run(actor, runId);
    if (!frozen.candidateId().equals(request.candidateId())
        || !frozen.positionId().equals(request.positionId())
        || !repository.start(actor.tenantId(), runId))
      throw new HrBusinessException("HR_RUN_STATE_CONFLICT", "任务状态已变更", 409);
    try {
      if (Instant.now().isAfter(frozen.deadlineAt()))
        throw new HrBusinessException("HR_RUN_TIMED_OUT", "任务已超时", 408);
      FrozenInput inputSnapshot = read(frozen.inputJson(), FrozenInput.class);
      var position = inputSnapshot.position();
      var config = inputSnapshot.config();
      Facts facts = inputSnapshot.facts();
      String factSnapshotId = inputSnapshot.factSnapshotId();
      ObjectNode input = json.createObjectNode();
      if (!config.bindings().isEmpty())
        input.set("expected_bindings", json.valueToTree(config.bindings()));
      input.put("candidate_ref", facts.candidateId());
      ArrayNode blocks = input.putArray("blocks");
      for (Block b : facts.blocks()) {
        ObjectNode n = blocks.addObject();
        n.put("block_id", b.id());
        n.put("text", b.text());
        if (b.page() != null) n.put("page", b.page());
      }
      RequirementsPlan plan = requirements(config);
      Map<String, String> expected = plan.criteria();
      ArrayNode requirements = input.putArray("requirements");
      expected.forEach(
          (id, criterion) ->
              requirements
                  .addObject()
                  .put("requirement_id", id)
                  .put(
                      "criterion",
                      semanticAtDate(
                          criterion,
                          LocalDate.ofInstant(frozen.createdAt(), ZoneId.of("Asia/Shanghai")))));
      if (!repository.run(actor.tenantId(), runId).status().equals("RUNNING")
          || Thread.currentThread().isInterrupted())
        throw new HrBusinessException("HR_RUN_CANCELLED", "任务已停止", 409);
      JsonNode data =
          expected.isEmpty()
              ? json.createObjectNode().set("assessments", json.createArrayNode())
              : gateway.execute(actor, 6103, frozen.scopeRef(), input);
      var validated = validateAssessments(data, expected.keySet(), facts.blocks());
      validated.putAll(
          HrDeterministicAssessments.evaluateAll(
              config.snapshot().criteria(),
              facts,
              LocalDate.ofInstant(frozen.createdAt(), ZoneId.of("Asia/Shanghai"))));
      List<HrAtomicAssessment> soft =
          config.snapshot().scoring().requirements().stream()
              .map(
                  r ->
                      r.applicable()
                          ? validated.get(r.id())
                          : new HrAtomicAssessment(
                              r.id(),
                              HrAtomicAssessment.Level.NOT_APPLICABLE,
                              null,
                              null,
                              List.of()))
              .toList();
      List<Result> hard = new ArrayList<>();
      for (var rule : config.snapshot().hardConditions()) {
        Type type = Type.valueOf(rule.type());
        Result decision;
        if (type == Type.REQUIRED_SKILL
            || type == Type.CERTIFICATE
            || type == Type.LOCATION
            || type == Type.LANGUAGE) {
          List<Status> statuses =
              plan.hardAtoms().get(rule.id()).stream()
                  .map(
                      id ->
                          semanticHardStatus(
                              rule,
                              validated.get(id),
                              config.snapshot().criteria().stream()
                                  .filter(c -> c.id().equals(rule.id()))
                                  .findFirst()
                                  .orElse(null)))
                  .toList();
          Result evaluated =
              new HrHardConditionEvaluator()
                  .combine(rule.id(), type, MatchMode.valueOf(semanticHardMode(rule)), statuses);
          decision =
              new Result(
                  rule.id(), type, evaluated.status(), rule.overridable(), evaluated.reasonCode());
        } else
          decision =
              numericCondition(
                  rule, facts, LocalDate.ofInstant(frozen.createdAt(), ZoneId.of("Asia/Shanghai")));
        hard.add(decision);
      }
      List<SemanticAssessment> source = new ArrayList<>(readSourceAssessments(data));
      for (var criterion : config.snapshot().criteria()) {
        if (criterion.calculation() == null) continue;
        var assessment = validated.get(criterion.id());
        String status =
            switch (assessment.level()) {
              case STRONG_MATCH -> "STRONG";
              case PARTIAL_MATCH -> "PARTIAL";
              default -> assessment.level().name();
            };
        List<Evidence> evidence =
            facts.structuredFacts().stream()
                .flatMap(f -> f.evidence().stream())
                .filter(e -> assessment.evidenceIds().contains(e.blockId()))
                .distinct()
                .limit(5)
                .toList();
        source.add(
            new SemanticAssessment(criterion.id(), status, "Java根据冻结规则和已确认事实确定计算", evidence));
      }
      SemanticAssessments assessmentSnapshot = new SemanticAssessments(soft, source);
      String semanticId = UUID.randomUUID().toString();
      SemanticSnapshot semantic =
          new SemanticSnapshot(
              semanticId,
              actor.tenantId(),
              facts.candidateId(),
              factSnapshotId,
              write(config),
              write(assessmentSnapshot),
              write(hard),
              Instant.now().toString());
      if (Instant.now().isAfter(frozen.deadlineAt()))
        throw new HrBusinessException("HR_RUN_TIMED_OUT", "任务已超时", 408);
      Matching result =
          score(
              actor,
              facts,
              factSnapshotId,
              position,
              config,
              semanticId,
              soft,
              hard,
              LocalDate.ofInstant(frozen.createdAt(), ZoneId.of("Asia/Shanghai")));
      Explanation explanation;
      if (!repository.run(actor.tenantId(), runId).status().equals("RUNNING")
          || Thread.currentThread().isInterrupted())
        throw new HrBusinessException("HR_RUN_CANCELLED", "任务已停止", 409);
      input.set("assessments", data.path("assessments"));
      if (config.context() != null)
        input.put("jd_text", Objects.toString(config.context().jdText(), ""));
      try {
        if (expected.isEmpty()) throw new IllegalStateException("NO_SEMANTIC_EXPLANATION_REQUIRED");
        explanation =
            validateExplanation(
                gateway.execute(actor, 6104, frozen.scopeRef(), input), source, facts.blocks());
      } catch (RuntimeException error) {
        explanation = new Explanation(List.of(), List.of(), "UNAVAILABLE");
      }
      result = assembler.details(result, explanation, List.of());
      result = assembler.evidence(result, source);
      if (authority != null) {
        var refreshed = authority.refresh(actor);
        var currentPosition = positions.get(refreshed, position.id());
        candidates.candidate(refreshed, facts.candidateId());
        HrAccessPolicy.requireFor(
            refreshed,
            "hr:matching:run",
            currentPosition.departmentId(),
            currentPosition.id(),
            "POSITION");
      }
      if (!repository.completeRun(actor.tenantId(), runId, semantic, toSnapshot(actor, result)))
        throw new HrBusinessException("HR_RUN_CANCELLED", "任务已停止", 409);
      return result;
    } catch (RuntimeException error) {
      String code =
          error instanceof HrBusinessException h ? h.code() : "HR_EVALUATION_CONTRACT_INVALID";
      if (repository.run(actor.tenantId(), runId).status().equals("RUNNING"))
        repository.finishRun(
            actor.tenantId(),
            runId,
            code.equals("HR_RUN_TIMED_OUT")
                ? "TIMED_OUT"
                : blockedCode(code) ? "BLOCKED" : "FAILED",
            null,
            code);
      if (error instanceof HrBusinessException h) throw h;
      throw new HrBusinessException(code, "评估未完成，未生成候选人结论", 422);
    }
  }

  private static boolean blockedCode(String code) {
    return code.startsWith("PAID_")
        || code.startsWith("BUDGET_")
        || code.startsWith("WORKLOAD_")
        || code.startsWith("LEDGER_")
        || java.util.Set.of("NO_BUDGET", "UNKNOWN_PRICE", "INVALID_PRICE", "INVALID_PLAN")
            .contains(code);
  }

  public com.aiep.aihub.api.hr.HrExecutionContracts.RecalculationPreview preview(
      HrActor actor, Recalculation request) {
    HrAccessPolicy.require(actor, "hr:matching:run");
    Position position = positions.get(actor, request.positionId());
    HrAccessPolicy.requireFor(
        actor, "hr:matching:run", position.departmentId(), position.id(), "POSITION");
    if (position.version() != request.expectedVersion()) throw HrPositionService.conflict();
    if (request.resultIds() == null
        || request.resultIds().isEmpty()
        || request.resultIds().size() > 100
        || request.weights() == null
        || request.thresholds() == null
        || request.thresholds().size() != 3) throw HrPositionService.invalid("重算参数无效");
    List<com.aiep.aihub.api.hr.HrExecutionContracts.PreviewItem> items = new ArrayList<>();
    List<Object> input = new ArrayList<>();
    input.add(
        java.util.Arrays.asList(
            request.positionId(),
            request.sourceConfigVersion(),
            request.weights(),
            request.thresholds(),
            request.mode(),
            request.expectedVersion()));
    for (String id : request.resultIds()) {
      Matching old = get(actor, id);
      if (!position.id().equals(old.positionId())
          || !Objects.equals(request.sourceConfigVersion(), old.configVersion()))
        throw HrPositionService.conflict();
      var fact = candidates.snapshot(actor, old.candidateId());
      if (!fact.id().equals(old.factSnapshotId())) throw HrPositionService.conflict();
      var semantic = repository.semantic(actor.tenantId(), old.semanticSnapshotId());
      if (semantic == null) throw HrPositionService.missing();
      ConfigVersion frozen = read(semantic.configJson(), ConfigVersion.class);
      var original = frozen.snapshot().scoring();
      var w = request.weights();
      HrFrozenConfig config;
      try {
        config =
            new HrFrozenConfig(
                original.version(),
                Map.of(
                    HrFrozenConfig.Dimension.SKILL,
                    w.skills(),
                    HrFrozenConfig.Dimension.EXPERIENCE,
                    w.experience(),
                    HrFrozenConfig.Dimension.PROJECT,
                    w.projects(),
                    HrFrozenConfig.Dimension.EDUCATION,
                    w.education(),
                    HrFrozenConfig.Dimension.BONUS,
                    w.bonus()),
                original.requirements(),
                request.thresholds().get(0),
                request.thresholds().get(1),
                request.thresholds().get(2),
                original.minimumCoverage(),
                original.strongCoverage());
      } catch (IllegalArgumentException e) {
        throw HrPositionService.invalid("权重或阈值无效");
      }
      var facts = candidates.decode(fact);
      var assessments = read(semantic.assessmentsJson(), SemanticAssessments.class);
      var score =
          new HrScoreEngine()
              .score(
                  config,
                  new HrVerifiedFacts(
                      readList(semantic.hardConditionsJson(), Result.class),
                      HrQualityPolicy.hasEvidenceConflict(facts) || facts.profile().name() == null),
                  assessments.atomic(),
                  activeOverrides(old.overrides()),
                  LocalDate.parse(old.asOfDate()));
      items.add(
          new com.aiep.aihub.api.hr.HrExecutionContracts.PreviewItem(
              id,
              old.candidateId(),
              old.totalScore() == null ? old.referenceScore() : old.totalScore(),
              score.totalScore() == null ? score.referenceScore() : score.totalScore(),
              score.businessStatus().name(),
              score.band() == null ? null : score.band().name(),
              score.evidenceCoverage()));
      input.add(List.of(old.snapshotHash(), fact.id(), frozen.snapshotHash()));
    }
    return new com.aiep.aihub.api.hr.HrExecutionContracts.RecalculationPreview(
        HrPositionService.hash(input), items, 0);
  }

  @org.springframework.transaction.annotation.Transactional
  public RunResponse recalculate(HrActor actor, Recalculation request) {
    HrAccessPolicy.require(actor, "hr:matching:run");
    if (request.previewHash() != null
        && !request.previewHash().equals(preview(actor, request).inputHash()))
      throw HrPositionService.conflict();
    Position position = positions.get(actor, request.positionId());
    HrAccessPolicy.requireFor(
        actor, "hr:matching:run", position.departmentId(), position.id(), "POSITION");
    if (request.resultIds() == null
        || request.resultIds().isEmpty()
        || request.resultIds().size() > 100
        || new HashSet<>(request.resultIds()).size() != request.resultIds().size()
        || request.weights() == null
        || request.thresholds() == null
        || request.thresholds().size() != 3
        || !Set.of("TEMPORARY", "DEFAULT").contains(request.mode()))
      throw HrPositionService.invalid("重算参数无效");
    if (position.version() != request.expectedVersion()) throw HrPositionService.conflict();
    var w = request.weights();
    Map<HrFrozenConfig.Dimension, Integer> weights =
        Map.of(
            HrFrozenConfig.Dimension.SKILL,
            w.skills(),
            HrFrozenConfig.Dimension.EXPERIENCE,
            w.experience(),
            HrFrozenConfig.Dimension.PROJECT,
            w.projects(),
            HrFrozenConfig.Dimension.EDUCATION,
            w.education(),
            HrFrozenConfig.Dimension.BONUS,
            w.bonus());
    String runId = UUID.randomUUID().toString();
    List<SemanticSnapshot> semantics = new ArrayList<>();
    List<ResultSnapshot> results = new ArrayList<>();
    // Validate all selections before writing any new result.
    List<Matching> selected = new ArrayList<>();
    Map<String, Snapshot> factSnapshots = new HashMap<>();
    Set<String> selectedCandidates = new HashSet<>();
    for (String id : request.resultIds()) {
      Matching m = get(actor, id);
      if (!m.positionId().equals(position.id())
          || !m.configVersion().equals(request.sourceConfigVersion()))
        throw HrPositionService.conflict();
      Snapshot snapshot = candidates.snapshot(actor, m.candidateId());
      if (!snapshot.id().equals(m.factSnapshotId()))
        throw new HrBusinessException("HR_FACT_SNAPSHOT_CHANGED", "事实已变更，需要重新进行语义评估", 409);
      if (!selectedCandidates.add(m.candidateId()))
        throw HrPositionService.invalid("每位候选人只能选择一个来源结果");
      factSnapshots.put(m.candidateId(), snapshot);
      selected.add(m);
    }
    if (request.mode().equals("DEFAULT")
        && !request.sourceConfigVersion().equals(position.configVersion()))
      throw HrPositionService.conflict();
    ConfigVersion published = null;
    String temporaryVersion =
        "adhoc-" + UUID.randomUUID().toString().replace("-", "").substring(0, 26);
    String temporaryConfigId = UUID.randomUUID().toString();
    for (Matching old : selected) {
      SemanticSnapshot semantic = repository.semantic(actor.tenantId(), old.semanticSnapshotId());
      if (semantic == null) throw HrPositionService.missing();
      ConfigVersion frozen = read(semantic.configJson(), ConfigVersion.class);
      var original = frozen.snapshot().scoring();
      HrFrozenConfig scoring;
      try {
        scoring =
            new HrFrozenConfig(
                temporaryVersion,
                weights,
                original.requirements(),
                request.thresholds().get(0),
                request.thresholds().get(1),
                request.thresholds().get(2),
                original.minimumCoverage(),
                original.strongCoverage());
      } catch (IllegalArgumentException e) {
        throw HrPositionService.invalid("权重或阈值无效");
      }
      Draft draft = frozen.snapshot();
      ConfigVersion config =
          new ConfigVersion(
              temporaryConfigId,
              frozen.positionId(),
              temporaryVersion,
              frozen.contextVersion(),
              new Draft(
                  draft.positionId(),
                  draft.name(),
                  draft.family(),
                  draft.departmentId(),
                  draft.level(),
                  draft.jdText(),
                  draft.lastStep(),
                  scoring,
                  draft.hardConditions(),
                  draft.criteria(),
                  draft.version(),
                  null,
                  draft.visibleMarks()),
              HrPositionService.hash(scoring),
              frozen.publishedBy(),
              frozen.publishedAt(),
              frozen.dictionaryVersion(),
              frozen.bindings(),
              frozen.context());
      if (request.mode().equals("DEFAULT")) {
        if (published == null)
          published =
              positions.publishScoring(actor, position.id(), request.expectedVersion(), scoring);
        config = published;
      }
      Facts facts = candidates.decode(factSnapshots.get(old.candidateId()));
      var assessmentSnapshot = read(semantic.assessmentsJson(), SemanticAssessments.class);
      var assessments = assessmentSnapshot.atomic();
      var hard = readList(semantic.hardConditionsJson(), Result.class);
      String semanticId = UUID.randomUUID().toString();
      var revisedSemantic =
          new SemanticSnapshot(
              semanticId,
              actor.tenantId(),
              old.candidateId(),
              old.factSnapshotId(),
              write(config),
              semantic.assessmentsJson(),
              write(hard),
              Instant.now().toString());
      Matching result =
          score(
              actor,
              facts,
              old.factSnapshotId(),
              position,
              config,
              semanticId,
              assessments,
              hard,
              LocalDate.parse(old.asOfDate()),
              activeOverrides(old.overrides()));
      result = assembler.details(result, old.explanation(), old.overrides());
      result = assembler.evidence(result, assessmentSnapshot.source());
      ResultSnapshot snapshot = toSnapshot(actor, result);
      if (request.mode().equals("TEMPORARY"))
        snapshot =
            new ResultSnapshot(
                snapshot.id(),
                snapshot.tenantId(),
                snapshot.candidateId(),
                snapshot.positionId(),
                snapshot.factSnapshotId(),
                snapshot.configVersion(),
                snapshot.contextVersion(),
                snapshot.semanticSnapshotId(),
                snapshot.resultJson(),
                "TEMPORARY",
                null,
                snapshot.createdAt(),
                snapshot.businessStatus(),
                snapshot.totalScore(),
                snapshot.evidenceCoverage(),
                snapshot.band());
      semantics.add(revisedSemantic);
      results.add(snapshot);
    }
    Run run =
        new Run(
            runId,
            actor.tenantId(),
            selected.getFirst().candidateId(),
            position.id(),
            "PENDING",
            null,
            null,
            Instant.now(),
            write(request),
            Instant.now().plusSeconds(600),
            "recalc-" + runId,
            HrPositionService.hash(request),
            "hr-" + runId);
    repository.insertRun(run);
    if (!repository.start(actor.tenantId(), runId)) throw HrPositionService.conflict();
    if (!repository.completeBatch(actor.tenantId(), runId, semantics, results))
      throw HrPositionService.conflict();
    return new RunResponse(runId, "SUCCEEDED");
  }

  @org.springframework.transaction.annotation.Transactional
  public Matching recalculate(HrActor actor, String resultId) {
    HrAccessPolicy.require(actor, "hr:matching:run");
    Matching old = get(actor, resultId);
    var snapshot = candidates.snapshot(actor, old.candidateId());
    Facts facts = candidates.decode(snapshot);
    if (!snapshot.id().equals(old.factSnapshotId()))
      throw new HrBusinessException("HR_FACT_SNAPSHOT_CHANGED", "事实已变更，需要重新进行语义评估", 409);
    var semantic = repository.semantic(actor.tenantId(), old.semanticSnapshotId());
    if (semantic == null) throw HrPositionService.missing();
    ConfigVersion config = read(semantic.configJson(), ConfigVersion.class);
    SemanticAssessments assessmentSnapshot =
        read(semantic.assessmentsJson(), SemanticAssessments.class);
    List<HrAtomicAssessment> assessments = assessmentSnapshot.atomic();
    List<Result> hard = readList(semantic.hardConditionsJson(), Result.class);
    var position = positions.get(actor, old.positionId());
    HrAccessPolicy.requireFor(
        actor, "hr:matching:run", position.departmentId(), position.id(), "POSITION");
    Matching result =
        score(
            actor,
            facts,
            snapshot.id(),
            position,
            config,
            semantic.id(),
            assessments,
            hard,
            LocalDate.parse(old.asOfDate()),
            activeOverrides(old.overrides()));
    result = assembler.details(result, old.explanation(), old.overrides());
    result = assembler.evidence(result, assessmentSnapshot.source());
    String runId = UUID.randomUUID().toString();
    Run run =
        new Run(
            runId,
            actor.tenantId(),
            old.candidateId(),
            old.positionId(),
            "PENDING",
            null,
            null,
            Instant.now(),
            write(new MatchRequest(old.candidateId(), old.positionId(), facts.version())),
            Instant.now().plusSeconds(600),
            "recalc-" + runId,
            HrPositionService.hash(List.of(old.resultId(), old.snapshotHash())),
            "hr-" + runId);
    repository.insertRun(run);
    if (!repository.start(actor.tenantId(), runId)
        || !repository.completeBatch(
            actor.tenantId(),
            runId,
            Collections.singletonList(null),
            List.of(toSnapshot(actor, result)))) throw HrPositionService.conflict();
    return result;
  }

  public Matching override(HrActor actor, String resultId, OverrideRequest request) {
    HrAccessPolicy.require(actor, "hr:matching:override");
    HrAccessPolicy.require(actor, "hr:matching:run");
    String reason = overrideReason(request.reason());
    OverrideInputs input = overrideInputs(actor, resultId, request.expectedSnapshotHash());
    if (request.conditionIds() == null
        || request.conditionIds().isEmpty()
        || new HashSet<>(request.conditionIds()).size() != request.conditionIds().size())
      throw new HrBusinessException("HR_OVERRIDE_INVALID", "请选择不重复的明确失败条件", 422);
    Set<String> active = activeOverrides(input.original().overrides());
    List<OverrideView> events = new ArrayList<>(input.original().overrides());
    for (String conditionId : request.conditionIds()) {
      Result condition =
          input.hard().stream()
              .filter(c -> c.id().equals(conditionId))
              .findFirst()
              .orElseThrow(() -> new HrBusinessException("HR_OVERRIDE_INVALID", "放行条件不存在", 422));
      HardRule rule =
          input.config().snapshot().hardConditions().stream()
              .filter(r -> r.id().equals(conditionId))
              .findFirst()
              .orElseThrow();
      if (condition.status() != Status.FAIL
          || !condition.overrideAllowed()
          || !rule.overridable()
          || active.contains(conditionId))
        throw new HrBusinessException("HR_OVERRIDE_NOT_ALLOWED", "该条件不能人工放行或已被放行", 422);
      active.add(conditionId);
      events.add(
          new OverrideView(
              UUID.randomUUID().toString(),
              conditionId,
              reason,
              actor.userId(),
              Instant.now().toString(),
              "GRANTED",
              null));
    }
    return saveOverride(actor, input, active, events);
  }

  public Matching revokeOverride(HrActor actor, String resultId, RevokeOverrideRequest request) {
    HrAccessPolicy.require(actor, "hr:matching:override");
    HrAccessPolicy.require(actor, "hr:matching:run");
    String reason = overrideReason(request.reason());
    OverrideInputs input = overrideInputs(actor, resultId, request.expectedSnapshotHash());
    OverrideView grant =
        input.original().overrides().stream()
            .filter(
                event ->
                    event.id().equals(request.overrideId()) && event.action().equals("GRANTED"))
            .findFirst()
            .orElseThrow(() -> new HrBusinessException("HR_OVERRIDE_INVALID", "放行记录不存在", 422));
    if (input.original().overrides().stream()
        .anyMatch(event -> request.overrideId().equals(event.revokedOverrideId())))
      throw new HrBusinessException("HR_OVERRIDE_ALREADY_REVOKED", "该放行已撤销", 409);
    Set<String> active = activeOverrides(input.original().overrides());
    if (!active.remove(grant.conditionId()))
      throw new HrBusinessException("HR_OVERRIDE_ALREADY_REVOKED", "该放行已撤销", 409);
    List<OverrideView> events = new ArrayList<>(input.original().overrides());
    events.add(
        new OverrideView(
            UUID.randomUUID().toString(),
            grant.conditionId(),
            reason,
            actor.userId(),
            Instant.now().toString(),
            "REVOKED",
            grant.id()));
    return saveOverride(actor, input, active, events);
  }

  private record OverrideInputs(
      Matching original,
      Facts facts,
      ConfigVersion config,
      Position position,
      List<HrAtomicAssessment> assessments,
      List<Result> hard,
      List<SemanticAssessment> source) {}

  private OverrideInputs overrideInputs(HrActor actor, String resultId, String expectedHash) {
    Matching old = get(actor, resultId);
    var authorizedPosition = positions.get(actor, old.positionId());
    HrAccessPolicy.requireFor(
        actor,
        "hr:matching:override",
        authorizedPosition.departmentId(),
        authorizedPosition.id(),
        "POSITION");
    HrAccessPolicy.requireFor(
        actor,
        "hr:matching:run",
        authorizedPosition.departmentId(),
        authorizedPosition.id(),
        "POSITION");
    if (expectedHash == null || !expectedHash.equals(old.snapshotHash()))
      throw HrPositionService.conflict();
    ResultSnapshot stored = repository.result(actor.tenantId(), resultId);
    if (!stored.status().equals("CURRENT")) throw HrPositionService.conflict();
    Snapshot snapshot = candidates.snapshot(actor, old.candidateId());
    if (!snapshot.id().equals(old.factSnapshotId()))
      throw new HrBusinessException("HR_FACT_SNAPSHOT_CHANGED", "事实已变更，请先重新评估", 409);
    SemanticSnapshot semantic = repository.semantic(actor.tenantId(), old.semanticSnapshotId());
    if (semantic == null) throw HrPositionService.missing();
    SemanticAssessments assessments = read(semantic.assessmentsJson(), SemanticAssessments.class);
    return new OverrideInputs(
        old,
        candidates.decode(snapshot),
        read(semantic.configJson(), ConfigVersion.class),
        positions.get(actor, old.positionId()),
        assessments.atomic(),
        readList(semantic.hardConditionsJson(), Result.class),
        assessments.source());
  }

  private Matching saveOverride(
      HrActor actor, OverrideInputs input, Set<String> active, List<OverrideView> events) {
    Matching old = input.original();
    Matching result =
        score(
            actor,
            input.facts(),
            old.factSnapshotId(),
            input.position(),
            input.config(),
            old.semanticSnapshotId(),
            input.assessments(),
            input.hard(),
            LocalDate.parse(old.asOfDate()),
            active);
    result = assembler.details(result, old.explanation(), events);
    result = assembler.evidence(result, input.source());
    if (!repository.replaceCurrent(actor.tenantId(), old.resultId(), toSnapshot(actor, result)))
      throw HrPositionService.conflict();
    return result;
  }

  private static String overrideReason(String reason) {
    if (reason == null || reason.isBlank() || reason.codePointCount(0, reason.length()) > 500)
      throw new HrBusinessException("HR_OVERRIDE_REASON_REQUIRED", "放行或撤销原因须为1至500字", 422);
    return reason.strip();
  }

  private static Set<String> activeOverrides(List<OverrideView> events) {
    Set<String> active = new HashSet<>();
    for (OverrideView event : events) {
      if (event.action().equals("GRANTED")) active.add(event.conditionId());
      else if (event.action().equals("REVOKED")) active.remove(event.conditionId());
      else throw new IllegalStateException("HR_OVERRIDE_EVENT_INVALID");
    }
    return active;
  }

  private Matching score(
      HrActor actor,
      Facts facts,
      String snapshotId,
      Position position,
      ConfigVersion config,
      String semanticId,
      List<HrAtomicAssessment> assessments,
      List<Result> hard,
      LocalDate asOfDate) {
    return score(
        actor,
        facts,
        snapshotId,
        position,
        config,
        semanticId,
        assessments,
        hard,
        asOfDate,
        Set.of());
  }

  private Matching score(
      HrActor actor,
      Facts facts,
      String snapshotId,
      Position position,
      ConfigVersion config,
      String semanticId,
      List<HrAtomicAssessment> assessments,
      List<Result> hard,
      LocalDate asOfDate,
      Set<String> overrides) {
    var score =
        new HrScoreEngine()
            .score(
                config.snapshot().scoring(),
                new HrVerifiedFacts(
                    hard,
                    HrQualityPolicy.hasEvidenceConflict(facts) || facts.profile().name() == null),
                assessments,
                overrides,
                asOfDate);
    return assembler.assemble(
        actor,
        UUID.randomUUID().toString(),
        facts,
        snapshotId,
        position,
        config,
        semanticId,
        score,
        assessments);
  }

  private record RequirementsPlan(
      Map<String, String> criteria, Map<String, List<String>> hardAtoms) {}

  private static RequirementsPlan requirements(ConfigVersion config) {
    var shared = HrTrialEvaluator.plan(config.snapshot());
    return new RequirementsPlan(shared.requirements(), shared.hardAtoms());
  }

  private static String anchoredCriterion(SemanticCriterion c) {
    return c.criterion()
        + " 强匹配:"
        + c.strongAnchor()
        + " 匹配:"
        + c.matchAnchor()
        + " 部分:"
        + c.partialAnchor()
        + " 明确不符合:"
        + c.notMetAnchor();
  }

  private static Status hardStatus(HrAtomicAssessment a) {
    return switch (a.level()) {
      case STRONG_MATCH, MATCH -> Status.PASS;
      case EXPLICIT_NOT_MET -> Status.FAIL;
      case NEEDS_REVIEW -> Status.NEEDS_REVIEW;
      default -> Status.UNKNOWN;
    };
  }

  public static List<String> semanticHardValues(HardRule rule) {
    if (rule.values() != null && !rule.values().isEmpty()) return rule.values();
    if ("LANGUAGE".equals(rule.type()) && rule.expected() != null && !rule.expected().isBlank())
      return List.of(rule.expected());
    throw HrPositionService.invalid("硬条件缺少原子标准");
  }

  public static String semanticHardMode(HardRule rule) {
    return "LANGUAGE".equals(rule.type()) && (rule.values() == null || rule.values().isEmpty())
        ? "ALL"
        : rule.matchMode();
  }

  public static Status semanticHardStatus(HardRule rule, HrAtomicAssessment assessment) {
    if (assessment == null
        || "LANGUAGE".equals(rule.type())
            && (rule.unit() == null || rule.unit().isBlank() || !languageLevelsValid(rule)))
      return Status.UNKNOWN;
    if ("LANGUAGE".equals(rule.type())
        && assessment.level() == HrAtomicAssessment.Level.PARTIAL_MATCH)
      return rule.tolerance() != null && rule.tolerance().signum() > 0
          ? Status.BORDERLINE
          : Status.FAIL;
    return hardStatus(assessment);
  }

  public static Status semanticHardStatus(
      HardRule rule, HrAtomicAssessment assessment, SemanticCriterion anchor) {
    if ("LANGUAGE".equals(rule.type()) && !languageAnchors(rule, anchor)) return Status.UNKNOWN;
    return semanticHardStatus(rule, assessment);
  }

  static boolean languageLevelsValid(HardRule rule) {
    return rule.threshold() != null
        && rule.threshold().signum() > 0
        && rule.threshold().stripTrailingZeros().scale() <= 0
        && (rule.tolerance() == null
            || rule.tolerance().signum() >= 0
                && rule.tolerance().stripTrailingZeros().scale() <= 0
                && rule.tolerance().compareTo(
                    rule.threshold().multiply(new java.math.BigDecimal("0.30"))
                        .setScale(0, java.math.RoundingMode.FLOOR)) <= 0);
  }

  public static boolean languageAnchors(HardRule rule, SemanticCriterion anchor) {
    return languageLevelsValid(rule)
        && rule.unit() != null
        && !rule.unit().isBlank()
        && anchor != null
        && java.util.stream.Stream.of(
                anchor.criterion(),
                anchor.strongAnchor(),
                anchor.matchAnchor(),
                anchor.partialAnchor(),
                anchor.notMetAnchor())
            .allMatch(v -> v != null && !v.isBlank());
  }

  public static String semanticHardText(HardRule rule, SemanticCriterion anchor, String value) {
    if ("LANGUAGE".equals(rule.type())) {
      if (!languageAnchors(rule, anchor))
        return "语言标准缺少明确同考试体系/等级锚点，此原子仅可返回UNKNOWN；禁止自行补等级顺序或跨考试换算。";
      return anchoredCriterion(anchor)
          + "；只核验语言原子："
          + value
          + "；考试体系："
          + rule.unit()
          + "；配置容差："
          + Objects.toString(rule.tolerance(), "0")
          + "；仅按上述明确等级顺序和四档锚点判断，不按原始数字高低猜测。跨考试没有本配置明确对照规则一律UNKNOWN；缺失等级/规则或未提及时UNKNOWN；存在冲突NEEDS_REVIEW。"
          + (rule.tolerance() != null && rule.tolerance().signum() > 0
              ? "PARTIAL只表示明确落在配置容差档，低于容差须EXPLICIT_NOT_MET。"
              : "容差为0，PARTIAL表示明确低于标准，按FAIL处理。");
    }
    return anchoredCriterion(anchor)
        + "；仅判断此原子标准值："
        + value
        + "；条件类型："
        + rule.type()
        + "；仅依据明确工作/项目/有效证书或地域意愿，不推测未提及事实。";
  }

  public static String semanticAtDate(String criterion, LocalDate date) {
    String text = criterion + "；冻结评估日：" + date + "（仅供证书有效性及语言证书时效核验，不用模型计算工龄）。";
    if (text.codePointCount(0, text.length()) > 1000)
      throw HrPositionService.invalid("语义标准加评估日后超过1000字");
    return text;
  }

  private List<SemanticAssessment> readSourceAssessments(JsonNode data) {
    try {
      return json.convertValue(
          data.get("assessments"),
          json.getTypeFactory().constructCollectionType(List.class, SemanticAssessment.class));
    } catch (IllegalArgumentException e) {
      throw new HrBusinessException("HR_EVALUATION_CONTRACT_INVALID", "原子判断格式不符合契约", 422);
    }
  }

  public static Explanation validateExplanation(
      JsonNode data, List<SemanticAssessment> assessments, List<Block> blocks) {
    Map<String, SemanticAssessment> source = new HashMap<>();
    for (SemanticAssessment assessment : assessments)
      source.put(assessment.requirementId(), assessment);
    if (data.path("highlights").size() > 5 || data.path("gaps").size() > 4)
      throw new IllegalArgumentException("explanation exceeds business limits");
    String summary = data.has("summary") ? data.path("summary").asText(null) : "";
    HrProtectedAttributes.validateRule(summary);
    if (data.has("summary") && !data.path("summary").isTextual()
        || summary == null
        || summary.codePointCount(0, summary.length()) > 80)
      throw new IllegalArgumentException("invalid explanation summary");
    if (!summary.isEmpty()
        && assessments.stream()
            .filter(item -> item.evidence() != null && !item.evidence().isEmpty())
            .noneMatch(
                item ->
                    item.reason() != null && item.reason().contains(summary)
                        || item.evidence().stream()
                            .anyMatch(quote -> quote.quote().contains(summary))))
      throw new IllegalArgumentException("summary invents unsupported facts");
    return new Explanation(
        explanationItems(data.path("highlights"), true, source, blocks),
        explanationItems(data.path("gaps"), false, source, blocks),
        "COMPLETE",
        additionalExplanationItems(data, "verification_points", 4, source, blocks),
        additionalExplanationItems(data, "quality_notes", 3, source, blocks),
        summary);
  }

  private static List<ExplanationItem> additionalExplanationItems(
      JsonNode data,
      String key,
      int limit,
      Map<String, SemanticAssessment> source,
      List<Block> blocks) {
    if (!data.has(key)) return List.of();
    JsonNode items = data.path(key);
    if (!items.isArray() || items.size() > limit)
      throw new IllegalArgumentException("invalid bounded explanation items");
    return explanationItems(items, null, source, blocks);
  }

  private static List<ExplanationItem> explanationItems(
      JsonNode items,
      Boolean positive,
      Map<String, SemanticAssessment> source,
      List<Block> blocks) {
    if (!items.isArray() || items.size() > 10)
      throw new IllegalArgumentException("invalid explanation items");
    List<ExplanationItem> result = new ArrayList<>();
    for (JsonNode item : items) {
      String text = item.path("text").asText();
      HrProtectedAttributes.validateRule(text);
      if (text.isBlank()
          || text.codePointCount(0, text.length()) > 300
          || !item.path("requirement_ids").isArray()
          || item.get("requirement_ids").isEmpty()
          || item.get("requirement_ids").size() > 5
          || !item.path("evidence").isArray()
          || item.get("evidence").isEmpty()
          || item.get("evidence").size() > 5)
        throw new IllegalArgumentException("invalid explanation item");
      List<String> ids = new ArrayList<>();
      Set<Evidence> allowed = new HashSet<>();
      for (JsonNode requirement : item.get("requirement_ids")) {
        SemanticAssessment assessment = source.get(requirement.asText());
        if (assessment == null
            || Boolean.TRUE.equals(positive)
                && !Set.of("STRONG", "MATCH").contains(assessment.status())
            || Boolean.FALSE.equals(positive)
                && Set.of("STRONG", "MATCH").contains(assessment.status()))
          throw new IllegalArgumentException("explanation references unconfirmed judgment");
        ids.add(assessment.requirementId());
        allowed.addAll(assessment.evidence());
      }
      List<Evidence> evidence = new ArrayList<>();
      for (JsonNode quote : item.get("evidence")) {
        Evidence reference =
            new Evidence(
                quote.path("block_id").asText(),
                quote.path("start").asInt(-1),
                quote.path("end").asInt(-1),
                quote.path("quote").asText());
        if (!allowed.contains(reference))
          throw new IllegalArgumentException("explanation invents evidence");
        Block block =
            blocks.stream()
                .filter(b -> b.id().equals(reference.blockId()))
                .findFirst()
                .orElseThrow();
        HrCandidateService.validateEvidence(
            block.text(), reference.start(), reference.end(), reference.quote());
        evidence.add(reference);
      }
      result.add(new ExplanationItem(text, List.copyOf(evidence), List.copyOf(ids)));
    }
    return List.copyOf(result);
  }

  public static Result numericCondition(HardRule rule, Facts facts, LocalDate asOfDate) {
    Type type = Type.valueOf(rule.type());
    java.math.BigDecimal min = null, max = null;
    boolean conflict = false;
    if (type == Type.EDUCATION) {
      StructuredFact education =
          HrFactMeasurements.education(facts.structuredFacts(), facts.fields());
      if (education != null)
        min =
            max =
                java.math.BigDecimal.valueOf(HrFactMeasurements.educationRank(education.degree()));
    }
    if (type == Type.WORK_EXPERIENCE) {
      var bounds = HrFactMeasurements.experience(facts.structuredFacts(), facts.fields(), asOfDate);
      if (bounds != null) {
        min = java.math.BigDecimal.valueOf(bounds.minMonths());
        max = java.math.BigDecimal.valueOf(bounds.maxMonths());
        conflict = bounds.needsReview();
      }
    }
    if (type == Type.PROJECT_SCALE || type == Type.TEAM_SIZE) {
      Set<String> confirmed =
          facts.fields().stream()
              .filter(f -> "CONFIRMED".equals(f.status()))
              .map(Field::id)
              .collect(java.util.stream.Collectors.toSet());
      for (var fact : facts.structuredFacts()) {
        var m = fact.measurement();
        if (!"project".equals(fact.kind())
            || m == null
            || !confirmed.contains(fact.factId())
            || !fact.factId().equals(m.projectId())) continue;
        java.math.BigDecimal measured = null;
        if (type == Type.TEAM_SIZE && m.managedTeamSize() != null)
          measured = java.math.BigDecimal.valueOf(m.managedTeamSize());
        if (type == Type.PROJECT_SCALE
            && rule.values() != null
            && rule.values().contains(m.metric())
            && Objects.equals(rule.unit(), m.unit())) measured = m.value();
        if (measured != null && (min == null || measured.compareTo(min) > 0)) min = max = measured;
      }
    }
    if (rule.threshold() == null)
      return new Result(
          rule.id(), type, Status.UNKNOWN, rule.overridable(), "MEASUREMENT_UNAVAILABLE");
    java.math.BigDecimal required = rule.threshold(),
        tolerance = rule.tolerance() == null ? java.math.BigDecimal.ZERO : rule.tolerance();
    if (conflict)
      return new Result(
          rule.id(), type, Status.NEEDS_REVIEW, rule.overridable(), "MEASUREMENT_CONFLICT");
    if (min == null)
      return new Result(
          rule.id(), type, Status.UNKNOWN, rule.overridable(), "MEASUREMENT_UNAVAILABLE");
    Status status =
        min.compareTo(required) >= 0
            ? Status.PASS
            : min.compareTo(required.subtract(tolerance)) >= 0 && max.compareTo(required) < 0
                ? Status.BORDERLINE
                : max.compareTo(required.subtract(tolerance)) < 0 ? Status.FAIL : Status.UNKNOWN;
    return new Result(rule.id(), type, status, rule.overridable(), status.name());
  }

  public static Map<String, HrAtomicAssessment> validateAssessments(
      JsonNode data, Set<String> expected, List<Block> blocks) {
    Map<String, Block> byBlock = new HashMap<>();
    for (var b : blocks) byBlock.put(b.id(), b);
    Map<String, HrAtomicAssessment> result = new HashMap<>();
    if (!data.path("assessments").isArray()) throw new IllegalArgumentException();
    if (data.get("assessments").size() > 60) throw new IllegalArgumentException();
    for (JsonNode a : data.get("assessments")) {
      String id = a.path("requirement_id").asText();
      String reason = a.path("reason").asText();
      HrProtectedAttributes.validateRule(reason);
      if (!a.path("requirement_id").isTextual()
          || id.isBlank()
          || id.length() > 100
          || !a.path("reason").isTextual()
          || reason.isBlank()
          || reason.codePointCount(0, reason.length()) > 300)
        throw new IllegalArgumentException("invalid atomic assessment");
      var level =
          switch (a.path("status").asText()) {
            case "STRONG" -> HrAtomicAssessment.Level.STRONG_MATCH;
            case "MATCH" -> HrAtomicAssessment.Level.MATCH;
            case "PARTIAL" -> HrAtomicAssessment.Level.PARTIAL_MATCH;
            case "EXPLICIT_NOT_MET" -> HrAtomicAssessment.Level.EXPLICIT_NOT_MET;
            case "UNKNOWN" -> HrAtomicAssessment.Level.UNKNOWN;
            case "NEEDS_REVIEW" -> HrAtomicAssessment.Level.NEEDS_REVIEW;
            default -> throw new IllegalArgumentException();
          };
      List<String> evidence = new ArrayList<>();
      if (!a.path("evidence").isArray()) throw new IllegalArgumentException();
      for (JsonNode e : a.get("evidence")) {
        if (!e.path("start").isIntegralNumber()
            || !e.path("end").isIntegralNumber()
            || !e.path("quote").isTextual()
            || e.path("quote").asText().codePointCount(0, e.path("quote").asText().length()) > 1000)
          throw new IllegalArgumentException("invalid atomic evidence");
        Block b = byBlock.get(e.path("block_id").asText());
        if (b == null) throw new IllegalArgumentException();
        HrCandidateService.validateEvidence(
            b.text(), e.path("start").asInt(-1), e.path("end").asInt(-1), e.path("quote").asText());
        evidence.add(b.id());
      }
      if (result.put(id, new HrAtomicAssessment(id, level, null, null, evidence)) != null)
        throw new IllegalArgumentException();
    }
    if (!expected.equals(result.keySet())) throw new IllegalArgumentException();
    return result;
  }

  private ResultSnapshot toSnapshot(HrActor actor, Matching m) {
    return new ResultSnapshot(
        m.resultId(),
        actor.tenantId(),
        m.candidateId(),
        m.positionId(),
        m.factSnapshotId(),
        m.configVersion(),
        m.contextVersion(),
        m.semanticSnapshotId(),
        write(m),
        "CURRENT",
        null,
        m.createdAt(),
        m.businessStatus(),
        m.totalScore(),
        m.evidenceCoverage(),
        m.band());
  }

  private String write(Object value) {
    try {
      return codec.seal(json.writeValueAsString(value));
    } catch (Exception e) {
      throw new IllegalStateException("HR_SNAPSHOT_ENCODING_FAILED");
    }
  }

  private <T> T read(String value, Class<T> type) {
    try {
      return json.readValue(codec.open(value), type);
    } catch (Exception e) {
      throw new IllegalStateException("HR_SNAPSHOT_ENCODING_FAILED");
    }
  }

  private <T> List<T> readList(String value, Class<T> type) {
    try {
      return json.readValue(
          codec.open(value), json.getTypeFactory().constructCollectionType(List.class, type));
    } catch (Exception e) {
      throw new IllegalStateException("HR_SNAPSHOT_ENCODING_FAILED");
    }
  }
}

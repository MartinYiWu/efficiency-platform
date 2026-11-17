package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrPositionContracts.Draft;
import com.aiep.aihub.api.hr.HrTrialContracts.*;
import com.aiep.aihub.repository.hr.HrSettingsRepository;
import java.math.*;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 试跑冻结样本、种子与草稿；独立标注之后才返回对照。 */
@Service
public class HrTrialService {
  private static final Set<String> LABELS =
      Set.of(
          "STRONGLY_RECOMMENDED",
          "RECOMMENDED",
          "REVIEW",
          "NOT_RECOMMENDED",
          "FILTERED",
          "REVIEW_REQUIRED");
  private static final Set<String> REASONS =
      Set.of("HARD_CONDITION", "SKILL", "EXPERIENCE", "PROJECT", "EDUCATION", "EVIDENCE");
  private final HrSettingsRepository repository;
  private final HrPositionService positions;
  private final HrCandidateService candidates;
  private final HrTrialEvaluator evaluator;
  private HrReadinessService readiness;

  @org.springframework.beans.factory.annotation.Autowired
  public HrTrialService(
      HrSettingsRepository repository,
      HrPositionService positions,
      HrCandidateService candidates,
      HrTrialEvaluator evaluator,
      HrReadinessService readiness) {
    this(repository, positions, candidates, evaluator);
    this.readiness = readiness;
  }

  public HrTrialService(
      HrSettingsRepository repository,
      HrPositionService positions,
      HrCandidateService candidates,
      HrTrialEvaluator evaluator) {
    this.repository = repository;
    this.positions = positions;
    this.candidates = candidates;
    this.evaluator = evaluator;
  }

  public Trial create(HrActor actor, Create request) {
    HrAccessPolicy.require(actor, "hr:trial:run");
    HrAccessPolicy.require(actor, "hr:candidate:read");
    if (!Set.of(10, 20, 50).contains(request.sampleSize()))
      throw HrPositionService.invalid("预演样本数仅支持10/20/50");
    var p = positions.get(actor, request.positionId());
    HrAccessPolicy.requireFor(actor, "hr:trial:run", p.departmentId(), p.id(), "POSITION");
    var d = positions.draft(actor, p.id());
    if (p.version() != request.expectedPositionVersion()) throw HrPositionService.conflict();
    if (d.scoring() == null && d.draftScoring() != null)
      d =
          new Draft(
              d.positionId(),
              d.name(),
              d.family(),
              d.departmentId(),
              d.level(),
              d.jdText(),
              d.lastStep(),
              d.draftScoring().freeze(),
              d.hardConditions(),
              d.criteria(),
              d.version());
    HrPositionValidation.validate(d);
    List<String> ids =
        request.candidateIds() == null || request.candidateIds().isEmpty()
            ? new ArrayList<>(repository.candidateIds(actor, p.departmentId()))
            : new ArrayList<>(request.candidateIds());
    if (ids.size() != new HashSet<>(ids).size() || ids.size() > 10000)
      throw HrPositionService.invalid("预演样本重复或超过上限");
    ids.sort(String::compareTo);
    if (request.candidateIds() == null || request.candidateIds().isEmpty())
      Collections.shuffle(ids, new Random(request.seed()));
    ids = ids.stream().limit(request.sampleSize()).toList();
    if (ids.isEmpty()) throw HrPositionService.invalid("没有已授权的预演样本");
    var bindings =
        readiness == null
            ? Map.<String, com.aiep.aihub.api.hr.HrPositionContracts.AssetBinding>of()
            : readiness.bindings(actor);
    Long dictionaryVersion = null;
    LocalDate date = LocalDate.now(ZoneId.of("Asia/Shanghai"));
    List<TrialResult> results = new ArrayList<>();
    for (String id : ids) {
      var c = candidates.candidate(actor, id);
      if (!p.departmentId().equals(c.departmentId())) throw HrPositionService.missing();
      var facts = candidates.facts(actor, id);
      if (facts != null && facts.dictionaryVersion() != null) {
        if (dictionaryVersion != null && !dictionaryVersion.equals(facts.dictionaryVersion()))
          throw new HrBusinessException("HR_TRIAL_DICTIONARY_MIXED", "预演样本词典版本不同，请显式重归一后试跑", 409);
        dictionaryVersion = facts.dictionaryVersion();
      }
      results.add(evaluator.evaluateBound(actor, id, d, date, dictionaryVersion, bindings));
    }
    String status =
        results.stream().anyMatch(r -> !"SUCCEEDED".equals(r.status()))
            ? "BLOCKED_NEEDS_EVALUATION"
            : "COMPLETED";
    Trial trial =
        new Trial(
            UUID.randomUUID().toString(),
            p.id(),
            p.departmentId(),
            request.sampleSize(),
            ids.size(),
            request.seed(),
            HrPositionService.hash(d),
            1,
            status,
            results,
            List.of(),
            null,
            null,
            false,
            d,
            date,
            Map.of(),
            dictionaryVersion,
            bindings);
    repository.save(
        actor, "TRIAL", trial.id(), trial.departmentId(), 0, 1, trial, "CREATE_SANDBOX");
    return blind(trial);
  }

  private Trial raw(HrActor actor, String id) {
    HrAccessPolicy.require(actor, "hr:trial:read");
    HrAccessPolicy.require(actor, "hr:candidate:read");
    Trial t = repository.get(actor, "TRIAL", id, Trial.class);
    HrAccessPolicy.requireFor(actor, "hr:trial:read", t.departmentId(), t.positionId(), "POSITION");
    positions.get(actor, t.positionId());
    t.results().forEach(r -> candidates.candidate(actor, r.candidateId()));
    return t;
  }

  public Trial get(HrActor actor, String id) {
    return blind(raw(actor, id));
  }

  public List<Trial> list(HrActor actor, String positionId) {
    HrAccessPolicy.require(actor, "hr:trial:read");
    HrAccessPolicy.require(actor, "hr:candidate:read");
    positions.get(actor, positionId);
    return repository.list(actor, "TRIAL", Trial.class).stream()
        .filter(t -> t.positionId().equals(positionId))
        .map(t -> get(actor, t.id()))
        .toList();
  }

  @Transactional
  public Trial label(HrActor actor, String id, Labels input) {
    HrAccessPolicy.require(actor, "hr:trial:label");
    var old = raw(actor, id);
    HrAccessPolicy.requireFor(
        actor, "hr:trial:label", old.departmentId(), old.positionId(), "POSITION");
    if (old.version() != input.expectedVersion() || "RUNNING".equals(old.status()))
      throw HrPositionService.conflict();
    if (input.labels() == null || input.labels().isEmpty())
      throw HrPositionService.invalid("请提交独立标注");
    Map<String, Label> labels = new LinkedHashMap<>();
    old.labels().forEach(l -> labels.put(l.candidateId(), l));
    var allowed =
        old.results().stream()
            .map(TrialResult::candidateId)
            .collect(java.util.stream.Collectors.toSet());
    Set<String> submitted = new HashSet<>();
    for (var l : input.labels()) {
      if (l == null
          || !allowed.contains(l.candidateId())
          || !LABELS.contains(l.label())
          || !submitted.add(l.candidateId())
          || labels.containsKey(l.candidateId())
          || l.note() != null && l.note().length() > 200
          || l.reason() != null && !l.reason().isBlank() && !REASONS.contains(l.reason()))
        throw HrPositionService.invalid("标注无效、重复或备注超长");
      labels.put(l.candidateId(), l);
    }
    long denominator =
        old.results().stream()
            .filter(r -> r.label() != null && labels.containsKey(r.candidateId()))
            .count();
    long same =
        old.results().stream()
            .filter(
                r ->
                    r.label() != null
                        && labels.containsKey(r.candidateId())
                        && r.label().equals(labels.get(r.candidateId()).label()))
            .count();
    BigDecimal agreement =
        denominator == 0
            ? null
            : BigDecimal.valueOf(same * 100)
                .divide(BigDecimal.valueOf(denominator), 1, RoundingMode.HALF_UP);
    boolean fully = labels.size() == old.actualSize();
    String diagnosis =
        fully
            ? diagnose(
                old.results().stream()
                    .filter(r -> "SUCCEEDED".equals(r.status()))
                    .map(TrialResult::label)
                    .toList())
            : null;
    if (fully && old.results().stream().anyMatch(r -> "REVIEW_REQUIRED".equals(r.label())))
      diagnosis = "INSUFFICIENT_COVERAGE;" + diagnosis;
    Trial next =
        new Trial(
            old.id(),
            old.positionId(),
            old.departmentId(),
            old.sampleSize(),
            old.actualSize(),
            old.seed(),
            old.snapshotHash(),
            old.version() + 1,
            old.status(),
            old.results(),
            List.copyOf(labels.values()),
            diagnosis,
            fully ? agreement : null,
            fully
                && denominator >= 10
                && agreement != null
                && agreement.compareTo(BigDecimal.valueOf(85)) >= 0,
            old.frozenDraft(),
            old.asOfDate(),
            fully ? failureRates(old.results()) : Map.of(),
            old.dictionaryVersion(),
            old.bindings());
    repository.save(
        actor, "TRIAL", id, old.departmentId(), old.version(), next.version(), next, "BLIND_LABEL");
    return blind(next);
  }

  public ExecutionPlan plan(HrActor actor, String id, PlanRequest input) {
    var trial = raw(actor, id);
    HrAccessPolicy.requireFor(
        actor, "hr:trial:run", trial.departmentId(), trial.positionId(), "POSITION");
    if (trial.version() != input.expectedVersion() || "RUNNING".equals(trial.status()))
      throw HrPositionService.conflict();
    List<ExecutionOperation> operations = new ArrayList<>();
    int batches = (HrTrialEvaluator.plan(trial.frozenDraft()).requirements().size() + 14) / 15;
    for (var result : trial.results()) {
      if ("SUCCEEDED".equals(result.status())) continue;
      if (!"BLOCKED_NEEDS_EVALUATION".equals(result.status()))
        throw new HrBusinessException("HR_TRIAL_ALREADY_SUBMITTED", "失败或未知操作不能自动重发，请检查执行记录", 409);
      String runRef =
          "hr-trial-"
              + UUID.nameUUIDFromBytes(
                  (id + ":" + result.candidateId())
                      .getBytes(java.nio.charset.StandardCharsets.UTF_8));
      operations.add(
          new ExecutionOperation(result.candidateId(), result.factSnapshotId(), runRef, batches));
    }
    if (operations.size() * batches > 200) throw HrPositionService.invalid("预演工作量超过200个语义批次");
    var priorPlan =
        repository.exists(actor, "TRIAL_PLAN", id)
            ? repository.get(actor, "TRIAL_PLAN", id, ExecutionPlan.class)
            : null;
    long version = priorPlan == null ? 0 : priorPlan.version();
    String budgetRef = priorPlan == null ? null : priorPlan.budgetRef();
    String planRef = priorPlan == null ? null : priorPlan.planRef();
    String status = "READY", error = null;
    long cost = 0;
    int maximumCalls = operations.stream().mapToInt(o -> o.semanticBatches() * 3).sum();
    Instant deadline = null;
    try {
      var check =
          budgetRef == null
              ? evaluator.preflight(actor, id, operations)
              : evaluator.preflight(actor, id, operations, budgetRef, planRef);
      if (!check.path("ready").asBoolean())
        throw new HrBusinessException("HR_TRIAL_BUDGET_REQUIRED", "预演预算预检未通过", 409);
      cost = check.path("maximum_cost_microunits").asLong();
      if (check.path("maximum_calls").isIntegralNumber())
        maximumCalls = check.path("maximum_calls").asInt();
      if (check.hasNonNull("budget_ref")) budgetRef = check.path("budget_ref").asText();
      if (check.hasNonNull("plan_ref")) planRef = check.path("plan_ref").asText();
      if (!operations.isEmpty()
          && (budgetRef == null || budgetRef.isBlank() || planRef == null || planRef.isBlank()))
        throw new HrBusinessException("HR_TRIAL_BUDGET_REQUIRED", "预演缺少固定预算引用", 409);
      if (check.has("deadline_epoch_ms"))
        deadline = Instant.ofEpochMilli(check.path("deadline_epoch_ms").asLong());
    } catch (HrBusinessException e) {
      status = "BUDGET_REJECTED";
      error = e.code();
    }
    var plan =
        new ExecutionPlan(
            id,
            trial.departmentId(),
            trial.version(),
            version + 1,
            operations,
            maximumCalls,
            cost,
            status,
            error,
            deadline,
            budgetRef,
            planRef);
    repository.save(
        actor,
        "TRIAL_PLAN",
        id,
        trial.departmentId(),
        version,
        plan.version(),
        plan,
        "PLAN_WORKLOAD");
    return plan;
  }

  public ExecutionPlan executionPlan(HrActor actor, String id) {
    raw(actor, id);
    return repository.get(actor, "TRIAL_PLAN", id, ExecutionPlan.class);
  }

  public Trial execute(HrActor actor, String id, ExecuteRequest input) {
    var old = raw(actor, id);
    HrAccessPolicy.requireFor(
        actor, "hr:trial:run", old.departmentId(), old.positionId(), "POSITION");
    var plan = executionPlan(actor, id);
    if (old.version() != input.expectedVersion()
        || plan.trialVersion() != old.version()
        || plan.version() != input.expectedPlanVersion()
        || !"READY".equals(plan.status())
        || "RUNNING".equals(old.status())) throw HrPositionService.conflict();
    if (plan.deadline() != null && !plan.deadline().isAfter(Instant.now()))
      throw new HrBusinessException("BUDGET_STOPPED", "预演预算已过期", 409);
    var checked =
        evaluator.preflight(actor, id, plan.operations(), plan.budgetRef(), plan.planRef());
    if (!checked.path("ready").asBoolean()
        || !plan.operations().isEmpty()
            && (!Objects.equals(plan.budgetRef(), checked.path("budget_ref").asText())
                || !Objects.equals(plan.planRef(), checked.path("plan_ref").asText())))
      throw new HrBusinessException("BUDGET_REFERENCE_CHANGED", "预演预算引用已变更", 409);
    var running = withResults(old, old.results(), old.version() + 1, "RUNNING");
    repository.save(
        actor,
        "TRIAL",
        id,
        old.departmentId(),
        old.version(),
        running.version(),
        running,
        "START_SANDBOX");
    List<TrialResult> results = new ArrayList<>(old.results());
    String failure = null;
    for (var operation : plan.operations()) {
      String itemId =
          UUID.nameUUIDFromBytes(
                  (id + ":" + operation.candidateId())
                      .getBytes(java.nio.charset.StandardCharsets.UTF_8))
              .toString();
      if (repository.exists(actor, "TRIAL_ITEM", itemId))
        throw new HrBusinessException("HR_TRIAL_ALREADY_SUBMITTED", "此预演操作已提交，不自动重发", 409);
      var pending =
          new TrialResult(
              operation.candidateId(),
              "RUNNING",
              null,
              null,
              null,
              List.of(),
              operation.factSnapshotId(),
              null);
      repository.save(
          actor, "TRIAL_ITEM", itemId, old.departmentId(), 0, 1, pending, "CLAIM_OPERATION");
      TrialResult outcome;
      try {
        outcome =
            evaluator.execute(
                actor,
                operation.candidateId(),
                old.frozenDraft(),
                old.asOfDate(),
                operation.runRef(),
                operation.factSnapshotId(),
                plan.budgetRef(),
                plan.planRef(),
                old.dictionaryVersion(),
                old.bindings());
      } catch (HrBusinessException e) {
        failure = e.code();
        outcome =
            new TrialResult(
                operation.candidateId(),
                "SYSTEM_FAILED",
                null,
                null,
                null,
                List.of(),
                operation.factSnapshotId(),
                e.code());
      } catch (RuntimeException e) {
        failure = "HR_TRIAL_EXECUTION_FAILED";
        outcome =
            new TrialResult(
                operation.candidateId(),
                "SYSTEM_FAILED",
                null,
                null,
                null,
                List.of(),
                operation.factSnapshotId(),
                failure);
      }
      repository.save(
          actor, "TRIAL_ITEM", itemId, old.departmentId(), 1, 2, outcome, "FINISH_OPERATION");
      for (int i = 0; i < results.size(); i++)
        if (results.get(i).candidateId().equals(operation.candidateId())) results.set(i, outcome);
      if (failure != null
          && (failure.startsWith("BUDGET_")
              || failure.startsWith("PAID_")
              || failure.startsWith("PROVIDER_")
              || failure.equals("NO_BUDGET")
              || failure.equals("HR_IDENTITY_REQUIRED")
              || failure.equals("HR_PERMISSION_DENIED"))) break;
    }
    String status = failure == null ? "COMPLETED" : "BLOCKED_EXECUTION";
    Trial finished = withResults(old, results, running.version() + 1, status);
    repository.save(
        actor,
        "TRIAL",
        id,
        old.departmentId(),
        running.version(),
        finished.version(),
        finished,
        "FINISH_SANDBOX");
    return blind(finished);
  }

  private static Trial withResults(
      Trial old, List<TrialResult> results, long version, String status) {
    Map<String, Label> labels = new HashMap<>();
    old.labels().forEach(l -> labels.put(l.candidateId(), l));
    long count =
        results.stream()
            .filter(r -> r.label() != null && labels.containsKey(r.candidateId()))
            .count();
    long same =
        results.stream()
            .filter(
                r ->
                    r.label() != null
                        && labels.containsKey(r.candidateId())
                        && r.label().equals(labels.get(r.candidateId()).label()))
            .count();
    boolean fully = labels.size() == old.actualSize();
    BigDecimal agreement =
        fully && count > 0
            ? BigDecimal.valueOf(same * 100)
                .divide(BigDecimal.valueOf(count), 1, RoundingMode.HALF_UP)
            : null;
    String diagnosis =
        fully
            ? diagnose(
                results.stream()
                    .filter(r -> "SUCCEEDED".equals(r.status()))
                    .map(TrialResult::label)
                    .toList())
            : null;
    return new Trial(
        old.id(),
        old.positionId(),
        old.departmentId(),
        old.sampleSize(),
        old.actualSize(),
        old.seed(),
        old.snapshotHash(),
        version,
        status,
        results,
        old.labels(),
        diagnosis,
        agreement,
        fully
            && count >= 10
            && agreement != null
            && agreement.compareTo(BigDecimal.valueOf(85)) >= 0,
        old.frozenDraft(),
        old.asOfDate(),
        fully ? failureRates(results) : Map.of(),
        old.dictionaryVersion(),
        old.bindings());
  }

  private Trial blind(Trial t) {
    var labeled =
        t.labels().stream().map(Label::candidateId).collect(java.util.stream.Collectors.toSet());
    var results =
        t.results().stream()
            .map(
                r ->
                    labeled.contains(r.candidateId())
                        ? r
                        : new TrialResult(
                            r.candidateId(),
                            r.status(),
                            null,
                            null,
                            null,
                            List.of(),
                            r.factSnapshotId(),
                            r.errorCode()))
            .toList();
    return new Trial(
        t.id(),
        t.positionId(),
        t.departmentId(),
        t.sampleSize(),
        t.actualSize(),
        t.seed(),
        t.snapshotHash(),
        t.version(),
        t.status(),
        results,
        t.labels(),
        t.diagnosis(),
        t.agreement(),
        t.verified(),
        t.frozenDraft(),
        t.asOfDate(),
        t.hardConditionFailureRates(),
        t.dictionaryVersion(),
        t.bindings());
  }

  public static Map<String, BigDecimal> failureRates(List<TrialResult> results) {
    var successful = results.stream().filter(r -> "SUCCEEDED".equals(r.status())).toList();
    if (successful.isEmpty()) return Map.of();
    Map<String, Long> counts = new HashMap<>();
    successful.forEach(
        r -> new HashSet<>(r.failedConditionIds()).forEach(id -> counts.merge(id, 1L, Long::sum)));
    Map<String, BigDecimal> rates = new TreeMap<>();
    counts.forEach(
        (id, count) ->
            rates.put(
                id,
                BigDecimal.valueOf(count * 100)
                    .divide(BigDecimal.valueOf(successful.size()), 1, RoundingMode.HALF_UP)));
    return Map.copyOf(rates);
  }

  public static String diagnose(List<String> labels) {
    if (labels.isEmpty()) return "NO_VALID_RESULTS";
    long filtered = labels.stream().filter("FILTERED"::equals).count();
    if (filtered * 100 > labels.size() * 50L) return "HARD_CONDITIONS_TOO_STRICT";
    long scored =
        labels.stream().filter(l -> !Set.of("FILTERED", "REVIEW_REQUIRED").contains(l)).count();
    long low = labels.stream().filter("NOT_RECOMMENDED"::equals).count();
    long high =
        labels.stream()
            .filter(l -> Set.of("STRONGLY_RECOMMENDED", "RECOMMENDED").contains(l))
            .count();
    if (scored > 0 && low * 100 > scored * 70) return "SCORING_TOO_STRICT";
    if (scored > 0 && high * 100 > scored * 80) return "SCORING_TOO_LENIENT";
    if (new HashSet<>(labels).size() == 1) return "NO_DISCRIMINATION";
    return labels.contains("REVIEW_REQUIRED") ? "INSUFFICIENT_COVERAGE" : "BALANCED";
  }
}

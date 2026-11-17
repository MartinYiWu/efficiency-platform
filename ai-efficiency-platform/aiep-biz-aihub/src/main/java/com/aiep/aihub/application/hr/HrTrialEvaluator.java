package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.api.hr.HrPositionContracts.*;
import com.aiep.aihub.api.hr.HrTrialContracts.*;
import com.aiep.aihub.domain.hr.*;
import com.aiep.aihub.domain.hr.HrHardConditionEvaluator.*;
import com.aiep.aihub.repository.hr.HrMatchingRepository;
import com.fasterxml.jackson.databind.*;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Service;

/** 语义计划有界，缓存只复用同事实/标准；收费结果仅进入sandbox。 */
@Service
public class HrTrialEvaluator {
  private final HrCandidateService candidates;
  private final HrMatchingRepository matching;
  private final ObjectMapper json;
  private final HrSensitiveJsonCodec codec;
  private HrSemanticGateway gateway;
  private HrSourceAuthorization sources;

  public HrTrialEvaluator(
      HrCandidateService candidates,
      HrMatchingRepository matching,
      ObjectMapper json,
      HrSensitiveJsonCodec codec) {
    this.candidates = candidates;
    this.matching = matching;
    this.json = json;
    this.codec = codec;
  }

  @org.springframework.beans.factory.annotation.Autowired
  public HrTrialEvaluator(
      HrCandidateService candidates,
      HrMatchingRepository matching,
      ObjectMapper json,
      HrSensitiveJsonCodec codec,
      HrSemanticGateway gateway,
      HrSourceAuthorization sources) {
    this(candidates, matching, json, codec);
    this.gateway = gateway;
    this.sources = sources;
  }

  public record SemanticPlan(
      Map<String, String> requirements, Map<String, List<String>> hardAtoms) {
    public SemanticPlan {
      requirements = Map.copyOf(requirements);
      hardAtoms = Map.copyOf(hardAtoms);
    }
  }

  public static SemanticPlan plan(Draft draft) {
    Map<String, String> requirements = new LinkedHashMap<>();
    Map<String, List<String>> hardAtoms = new LinkedHashMap<>();
    for (var r : draft.scoring().requirements()) {
      if (!r.applicable()) continue;
      var c = criterion(draft, r.id());
      if (c.calculation() == null) requirements.put(r.id(), anchored(c));
    }
    for (var h : draft.hardConditions()) {
      if (!Set.of("REQUIRED_SKILL", "CERTIFICATE", "LOCATION", "LANGUAGE").contains(h.type()))
        continue;
      var anchor =
          "LANGUAGE".equals(h.type())
              ? draft.criteria().stream()
                  .filter(c -> c.id().equals(h.id()))
                  .findFirst()
                  .orElse(null)
              : criterion(draft, h.id());
      var values = HrMatchingService.semanticHardValues(h);
      if (!Set.of("ALL", "ANY").contains(HrMatchingService.semanticHardMode(h)))
        throw HrPositionService.invalid("硬条件匹配方式无效");
      List<String> ids = new ArrayList<>();
      for (int i = 0; i < values.size(); i++) {
        String id =
            values.size() == 1
                ? h.id()
                : "hard-" + HrPositionService.hash(List.of(h.id(), i)).substring(0, 32);
        requirements.put(id, HrMatchingService.semanticHardText(h, anchor, values.get(i)));
        ids.add(id);
      }
      hardAtoms.put(h.id(), List.copyOf(ids));
    }
    if (requirements.size() > 60) throw HrPositionService.invalid("语义原子超过60项");
    for (var value : requirements.values())
      HrMatchingService.semanticAtDate(value, LocalDate.of(2000, 1, 1));
    return new SemanticPlan(requirements, hardAtoms);
  }

  private static SemanticCriterion criterion(Draft d, String id) {
    return d.criteria().stream()
        .filter(c -> c.id().equals(id))
        .findFirst()
        .orElseThrow(() -> HrPositionService.invalid("要求缺少评分锚点"));
  }

  private static String anchored(SemanticCriterion c) {
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

  public TrialResult evaluate(HrActor actor, String candidateId, Draft draft, LocalDate date) {
    return evaluate(actor, candidateId, draft, date, null, null, null, Map.of());
  }

  public TrialResult evaluateBound(
      HrActor actor,
      String candidateId,
      Draft draft,
      LocalDate date,
      Long dictionaryVersion,
      Map<String, AssetBinding> bindings) {
    return evaluate(actor, candidateId, draft, date, null, null, dictionaryVersion, bindings);
  }

  public TrialResult execute(
      HrActor actor,
      String candidateId,
      Draft draft,
      LocalDate date,
      String runRef,
      String expectedSnapshot,
      String budgetRef,
      String planRef,
      Long dictionaryVersion,
      Map<String, AssetBinding> bindings) {
    var snapshot = candidates.snapshot(actor, candidateId);
    if (!snapshot.id().equals(expectedSnapshot))
      throw new HrBusinessException("HR_FACT_SNAPSHOT_CHANGED", "预演事实已变更，请新建预演", 409);
    var cached = evaluateBound(actor, candidateId, draft, date, dictionaryVersion, bindings);
    if ("SUCCEEDED".equals(cached.status())) return cached;
    var facts = candidates.facts(actor, candidateId);
    var plan = plan(draft);
    var input = json.createObjectNode().put("candidate_ref", candidateId);
    var blocks = input.putArray("blocks");
    for (var b : facts.blocks()) {
      var node = blocks.addObject().put("block_id", b.id()).put("text", b.text());
      if (b.page() != null) node.put("page", b.page());
    }
    if (budgetRef != null) input.put("workload_budget_ref", budgetRef);
    if (planRef != null) input.put("workload_plan_ref", planRef);
    if (!bindings.isEmpty()) input.set("expected_bindings", json.valueToTree(bindings));
    var req = input.putArray("requirements");
    plan.requirements()
        .forEach(
            (id, value) ->
                req.addObject()
                    .put("requirement_id", id)
                    .put("criterion", HrMatchingService.semanticAtDate(value, date)));
    JsonNode data = gateway.execute(actor, 6103, runRef, input);
    var validated =
        HrMatchingService.validateAssessments(data, plan.requirements().keySet(), facts.blocks());
    List<Result> hard = new ArrayList<>();
    for (var rule : draft.hardConditions()) {
      Type type = Type.valueOf(rule.type());
      if (plan.hardAtoms().containsKey(rule.id())) {
        List<Status> statuses =
            plan.hardAtoms().get(rule.id()).stream()
                .map(
                    id ->
                        HrMatchingService.semanticHardStatus(
                            rule,
                            validated.get(id),
                            draft.criteria().stream()
                                .filter(c -> c.id().equals(rule.id()))
                                .findFirst()
                                .orElse(null)))
                .toList();
        var decision =
            new HrHardConditionEvaluator()
                .combine(
                    rule.id(),
                    type,
                    MatchMode.valueOf(HrMatchingService.semanticHardMode(rule)),
                    statuses);
        hard.add(
            new Result(
                rule.id(), type, decision.status(), rule.overridable(), decision.reasonCode()));
      } else hard.add(HrMatchingService.numericCondition(rule, facts, date));
    }
    return evaluate(actor, candidateId, draft, date, validated, hard, dictionaryVersion, bindings);
  }

  public JsonNode preflight(HrActor actor, String trialId, List<ExecutionOperation> operations) {
    return preflight(actor, trialId, operations, null, null);
  }

  public JsonNode preflight(
      HrActor actor,
      String trialId,
      List<ExecutionOperation> operations,
      String expectedBudgetRef) {
    return preflight(actor, trialId, operations, expectedBudgetRef, null);
  }

  public JsonNode preflight(
      HrActor actor,
      String trialId,
      List<ExecutionOperation> operations,
      String expectedBudgetRef,
      String expectedPlanRef) {
    if (operations.isEmpty() && expectedBudgetRef == null)
      return json.createObjectNode()
          .put("ready", true)
          .put("maximum_calls", 0)
          .put("maximum_cost_microunits", 0);
    var input = json.createObjectNode();
    if (expectedBudgetRef != null) input.put("workload_budget_ref", expectedBudgetRef);
    if (expectedPlanRef != null) input.put("workload_plan_ref", expectedPlanRef);
    var workload = input.putArray("workload");
    for (var operation : operations)
      for (int i = 0; i < operation.semanticBatches(); i++)
        workload
            .addObject()
            .put("run_ref", operation.runRef())
            .put("skill_key", "hr.requirements.evaluate")
            .put("attempts", 3);
    return gateway.execute(actor, 6109, "hr-trial-plan-" + trialId, input);
  }

  private TrialResult evaluate(
      HrActor actor,
      String candidateId,
      Draft draft,
      LocalDate date,
      Map<String, HrAtomicAssessment> supplied,
      List<Result> suppliedHard,
      Long dictionaryVersion,
      Map<String, AssetBinding> bindings) {
    var candidate = candidates.candidate(actor, candidateId);
    if (sources != null) sources.requireMatching(actor, candidate, draft.positionId());
    if (!candidate.departmentId().equals(draft.departmentId())) throw HrPositionService.missing();
    var facts = candidates.facts(actor, candidateId);
    var snapshot = candidates.snapshot(actor, candidateId);
    Map<String, HrAtomicAssessment> atomic = new HashMap<>();
    List<Result> priorHard = suppliedHard == null ? List.of() : suppliedHard;
    if (supplied != null) atomic.putAll(supplied);
    else {
      var oldResults =
          matching.list(
              actor.tenantId(),
              actor.departmentIds(),
              draft.positionId(),
              candidateId,
              null,
              null,
              actor.positionIds(),
              actor.candidateIds(),
              0,
              100);
      for (var old : oldResults) {
        if (!snapshot.id().equals(old.factSnapshotId()) || old.semanticSnapshotId() == null)
          continue;
        var frozenResult = read(old.resultJson(), Matching.class);
        if (!date.toString().equals(frozenResult.asOfDate())) continue;
        var semantic = matching.semantic(actor.tenantId(), old.semanticSnapshotId());
        if (semantic == null || !snapshot.id().equals(semantic.factSnapshotId())) continue;
        var config = read(semantic.configJson(), ConfigVersion.class);
        if (!Objects.equals(dictionaryVersion, config.dictionaryVersion())
            || !bindings.equals(config.bindings())) continue;
        if (!HrPositionService.hash(config.snapshot().criteria())
                .equals(HrPositionService.hash(draft.criteria()))
            || !HrPositionService.hash(config.snapshot().hardConditions())
                .equals(HrPositionService.hash(draft.hardConditions()))) continue;
        var assessments = read(semantic.assessmentsJson(), SemanticAssessments.class);
        assessments.atomic().forEach(a -> atomic.put(a.requirementId(), a));
        try {
          priorHard =
              json.readerForListOf(Result.class)
                  .readValue(codec.open(semantic.hardConditionsJson()));
        } catch (Exception e) {
          throw new IllegalStateException("HR_TRIAL_SNAPSHOT_INVALID");
        }
        break;
      }
    }
    atomic.putAll(HrDeterministicAssessments.evaluateAll(draft.criteria(), facts, date));
    List<HrAtomicAssessment> soft = new ArrayList<>();
    for (var r : draft.scoring().requirements()) {
      if (!r.applicable()) {
        soft.add(
            new HrAtomicAssessment(
                r.id(), HrAtomicAssessment.Level.NOT_APPLICABLE, null, null, List.of()));
        continue;
      }
      if (!atomic.containsKey(r.id())) return blocked(candidateId, snapshot.id());
      soft.add(atomic.get(r.id()));
    }
    List<Result> hard = new ArrayList<>();
    for (var rule : draft.hardConditions()) {
      Type type = Type.valueOf(rule.type());
      if (Set.of(Type.REQUIRED_SKILL, Type.CERTIFICATE, Type.LOCATION, Type.LANGUAGE)
          .contains(type)) {
        var reused =
            priorHard.stream()
                .filter(h -> h.id().equals(rule.id()) && h.type() == type)
                .findFirst();
        if (reused.isEmpty()) return blocked(candidateId, snapshot.id());
        hard.add(reused.get());
      } else hard.add(HrMatchingService.numericCondition(rule, facts, date));
    }
    var score =
        new HrScoreEngine()
            .score(
                draft.scoring(),
                new HrVerifiedFacts(
                    hard,
                    soft.stream()
                        .anyMatch(a -> a.level() == HrAtomicAssessment.Level.NEEDS_REVIEW)),
                soft,
                Set.of(),
                date);
    String label =
        switch (score.businessStatus()) {
          case FILTERED -> "FILTERED";
          case REVIEW_REQUIRED -> "REVIEW_REQUIRED";
          case SCORED ->
              switch (score.band()) {
                case STRONG_RECOMMEND -> "STRONGLY_RECOMMENDED";
                case RECOMMEND -> "RECOMMENDED";
                case REVIEW -> "REVIEW";
                case NOT_RECOMMEND -> "NOT_RECOMMENDED";
              };
        };
    return new TrialResult(
        candidateId,
        "SUCCEEDED",
        label,
        score.referenceScore(),
        score.evidenceCoverage(),
        hard.stream().filter(h -> h.status() == Status.FAIL).map(Result::id).toList(),
        snapshot.id(),
        null);
  }

  private static TrialResult blocked(String candidate, String snapshot) {
    return new TrialResult(
        candidate,
        "BLOCKED_NEEDS_EVALUATION",
        null,
        null,
        null,
        List.of(),
        snapshot,
        "HR_TRIAL_BUDGET_REQUIRED");
  }

  private <T> T read(String value, Class<T> type) {
    try {
      return json.readValue(codec.open(value), type);
    } catch (Exception e) {
      throw new IllegalStateException("HR_TRIAL_SNAPSHOT_INVALID");
    }
  }
}


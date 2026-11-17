package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.platformai.api.AiInvocationException;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.*;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class HrSemanticGateway {
  private final AiInvokeFacade ai;
  private final ObjectMapper json;
  private HrActorAuthority authority;
  private com.aiep.aihub.repository.hr.HrBatchBudgetMapper batchBudgets;
  private com.aiep.aihub.repository.hr.HrBatchMapper batches;
  private com.aiep.aihub.repository.hr.HrExecutionMapper executions;
  private com.aiep.aihub.repository.hr.HrMatchingExecutionPlanMapper matchingPlans;
  private com.aiep.aihub.repository.hr.HrMatchingMapper matchingRuns;
  private com.aiep.aihub.repository.hr.HrCandidateMapper matchingCandidates;
  private com.aiep.aihub.repository.hr.HrPositionMapper matchingPositions;
  private HrSourceAuthorization matchingSources;

  public HrSemanticGateway(AiInvokeFacade ai, ObjectMapper json, HrActorAuthority authority) {
    this(ai, json);
    this.authority = authority;
  }

  public HrSemanticGateway(
      AiInvokeFacade ai,
      ObjectMapper json,
      HrActorAuthority authority,
      com.aiep.aihub.repository.hr.HrBatchBudgetMapper budgets,
      com.aiep.aihub.repository.hr.HrBatchMapper batches,
      com.aiep.aihub.repository.hr.HrExecutionMapper executions) {
    this(ai, json, authority);
    this.batchBudgets = budgets;
    this.batches = batches;
    this.executions = executions;
  }

  @org.springframework.beans.factory.annotation.Autowired
  public HrSemanticGateway(
      AiInvokeFacade ai,
      ObjectMapper json,
      HrActorAuthority authority,
      com.aiep.aihub.repository.hr.HrBatchBudgetMapper budgets,
      com.aiep.aihub.repository.hr.HrBatchMapper batches,
      com.aiep.aihub.repository.hr.HrExecutionMapper executions,
      com.aiep.aihub.repository.hr.HrMatchingExecutionPlanMapper matchingPlans,
      com.aiep.aihub.repository.hr.HrMatchingMapper matchingRuns,
      com.aiep.aihub.repository.hr.HrCandidateMapper matchingCandidates,
      com.aiep.aihub.repository.hr.HrPositionMapper matchingPositions,
      HrSourceAuthorization matchingSources) {
    this(ai, json, authority, budgets, batches, executions);
    this.matchingPlans = matchingPlans;
    this.matchingRuns = matchingRuns;
    this.matchingCandidates = matchingCandidates;
    this.matchingPositions = matchingPositions;
    this.matchingSources = matchingSources;
  }

  public HrSemanticGateway(AiInvokeFacade ai, ObjectMapper json) {
    this.ai = ai;
    this.json = json;
  }

  public JsonNode execute(HrActor actor, long skillId, String runId, ObjectNode input) {
    if (authority != null) actor = authority.refresh(actor);
    if (skillId == 6110) HrAccessPolicy.require(actor, "hr:candidate:read");
    if (skillId >= 6101 && skillId <= 6106)
      HrAccessPolicy.require(
          actor,
          switch ((int) skillId) {
            case 6101 ->
                runId.startsWith("jd-extract-") ? "hr:position:edit" : "hr:candidate:upload";
            case 6102 -> "hr:candidate:upload";
            case 6103, 6104 -> runId.startsWith("hr-trial-") ? "hr:trial:run" : "hr:matching:run";
            case 6105 -> "hr:interview:write";
            default -> "hr:position:edit";
          });
    if ((skillId == 6103 || skillId == 6104) && runId.startsWith("hr-match-")) {
      if (matchingPlans == null)
        throw new HrBusinessException("HR_MATCHING_PLAN_REQUIRED", "匹配任务未冻结执行预算", 409);
      var row = matchingPlans.find(actor.tenantId(), runId);
      if (row == null)
        throw new HrBusinessException("HR_MATCHING_PLAN_REQUIRED", "匹配任务未冻结执行预算", 409);
      try {
        var plan = json.readValue(row.payload(), HrMatchingExecutionPlans.Plan.class);
        if (!runId.equals(plan.scope()) || !row.runId().equals(plan.runId()))
          throw new HrBusinessException("HR_MATCHING_PLAN_REQUIRED", "匹配执行计划绑定无效", 409);
        var run = matchingRuns.run(actor.tenantId(), plan.runId());
        if (run == null || !runId.equals(run.scopeRef()) || !"RUNNING".equals(run.status()))
          throw new HrBusinessException("HR_RUN_CANCELLED", "匹配任务已停止或尚未执行", 409);
        var now = java.time.Instant.now();
        if (!plan.deadline().isAfter(now) || !run.deadlineAt().isAfter(now))
          throw new HrBusinessException("HR_RUN_TIMED_OUT", "匹配执行预算已截止", 408);
        var candidate = matchingCandidates.findActive(actor.tenantId(), run.candidateId(), now);
        var position = matchingPositions.find(actor.tenantId(), run.positionId());
        if (candidate == null || position == null) throw HrPositionService.missing();
        HrAccessPolicy.requireFor(
            actor, "hr:matching:run", position.departmentId(), position.id(), "POSITION");
        HrAccessPolicy.requireFor(
            actor, "hr:matching:read", position.departmentId(), position.id(), "POSITION");
        HrAccessPolicy.requireFor(
            actor, "hr:position:read", position.departmentId(), position.id(), "POSITION");
        matchingSources.requireMatching(actor, candidate, position.id());
        if (plan.cpuOnly()
            || plan.budgetRef() == null
            || plan.planRef() == null
            || plan.maximumAttempts() < 1
            || plan.maximumAttempts() > 3)
          throw new HrBusinessException("HR_MATCHING_PLAN_REQUIRED", "匹配模型执行计划无效", 409);
        input.put("workload_budget_ref", plan.budgetRef());
        input.put("workload_plan_ref", plan.planRef());
        input.put("maximum_attempts", plan.maximumAttempts());
      } catch (com.fasterxml.jackson.core.JsonProcessingException invalid) {
        throw new HrBusinessException("HR_MATCHING_PLAN_REQUIRED", "匹配执行计划无法验证", 409);
      }
    }
    if (skillId >= 6101
        && skillId <= 6104
        && runId.startsWith("hr-import-")
        && batchBudgets != null) {
      var item = batches.item(actor.tenantId(), runId.substring("hr-import-".length()));
      var parent = item == null ? null : batches.batch(actor.tenantId(), item.batchId());
      if (item == null
          || parent == null
          || java.util.Set.of("CANCELLED", "CANCEL_PENDING", "BLOCKED").contains(parent.status())
          || java.util.Set.of("CANCELLED", "CANCEL_PENDING").contains(item.status()))
        throw new HrBusinessException("HR_RUN_CANCELLED", "批次或材料已停止", 409);
      var budget = item == null ? null : batchBudgets.find(actor.tenantId(), item.batchId());
      if (budget == null) throw new HrBusinessException("HR_BATCH_BUDGET_REQUIRED", "批次未冻结预算", 409);
      try {
        String ref = json.readTree(budget.payload()).path("budgetRef").asText();
        if (ref.isBlank()) throw new IllegalArgumentException();
        input.put("workload_budget_ref", ref);
        String planRef = json.readTree(budget.payload()).path("planRef").asText();
        if (planRef.isBlank()) throw new IllegalArgumentException();
        input.put("workload_plan_ref", planRef);
        String limits = executions.getLimits(actor.tenantId(), item.batchId());
        int attempts = limits == null ? 0 : json.readTree(limits).path("maxAttempts").asInt();
        if (attempts < 1 || attempts > 3) throw new IllegalArgumentException();
        input.put("maximum_attempts", attempts);
      } catch (java.io.IOException | IllegalArgumentException e) {
        throw new HrBusinessException("HR_BATCH_BUDGET_REQUIRED", "批次预算无法验证", 409);
      }
    }
    boolean modelSkill =
        java.util.Set.of(6102L, 6103L, 6104L, 6105L, 6106L, 6110L).contains(skillId);
    if ((modelSkill || skillId == 6109) && !input.has("maximum_attempts") && batches != null) {
      var policy = batches.latestPolicy(actor.tenantId());
      try {
        int attempts =
            policy == null ? 3 : json.readTree(policy.payload()).path("maximumAttempts").asInt();
        if (attempts < 1 || attempts > 3) throw new IllegalArgumentException();
        input.put("maximum_attempts", attempts);
      } catch (java.io.IOException | IllegalArgumentException invalid) {
        throw new HrBusinessException("HR_RETRY_POLICY_INVALID", "模型尝试策略未就绪", 503);
      }
    }
    if (skillId == 6109 && !input.hasNonNull("workload_plan_ref")) {
      int maximum = input.path("maximum_attempts").asInt(3);
      for (var work : input.path("workload")) {
        if (work instanceof ObjectNode item)
          item.put("attempts", Math.min(maximum, item.path("attempts").asInt(3)));
      }
    }
    ObjectNode logicalInput = input.deepCopy();
    logicalInput.remove(java.util.List.of("contract_version", "run_id", "operation_id", "memory_context"));
    String operationId =
        UUID.nameUUIDFromBytes(
                (runId + ":" + skillId + ":" + HrPositionService.hash(logicalInput))
                    .getBytes(java.nio.charset.StandardCharsets.UTF_8))
            .toString();
    input.put("contract_version", "hr-skill/1");
    input.put("run_id", runId);
    input.put("operation_id", operationId);
    input.set(
        "memory_context",
        json.valueToTree(
            new MemoryContextEnvelope(
                "memory-context/1", "DISABLED",
                new MemoryContextEnvelope.Scope(
                    actor.tenantId(), actor.userId(), "hr", "hr", "TASK_ONLY", null),
                null)));
    try {
      var response =
          ai.executeSkill(
              new AiSkillExecuteRequest(
                  new AiRequestContext(
                      UUID.randomUUID().toString(), Long.valueOf(actor.userId()), "HR", "HR_SKILL"),
                  skillId,
                  json.writeValueAsString(input),
                  actor.tenantId()));
      ObjectMapper responseMapper = json;
      if (skillId == 6101 && input.path("extraction").path("archive_raw").asBoolean(false)) {
        responseMapper = json.copy();
        responseMapper
            .getFactory()
            .setStreamReadConstraints(
                com.fasterxml.jackson.core.StreamReadConstraints.builder()
                    .maxStringLength(28 * 1024 * 1024)
                    .build());
      }
      JsonNode result = responseMapper.readTree(response.content());
      if (!"hr-result/1".equals(result.path("contract_version").asText())
          || !runId.equals(result.path("run_id").asText())
          || !operationId.equals(result.path("operation_id").asText())
          || !result.path("data").isObject()) throw new IllegalArgumentException();
      return result.get("data");
    } catch (AiInvocationException error) {
      throw new HrBusinessException(error.code(), "AI执行被配置或预算门禁阻止", error.status());
    } catch (Exception error) {
      throw new HrBusinessException("HR_EVALUATION_UNAVAILABLE", "解析或评估未完成，请检查配置后重试", 503);
    }
  }

  public boolean cancel(HrActor actor, String runId) {
    try {
      return execute(actor, 6107, runId, json.createObjectNode())
          .path("cancelled")
          .asBoolean(false);
    } catch (HrBusinessException error) {
      return false;
    }
  }
}

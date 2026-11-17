package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.repository.hr.*;
import com.aiep.aihub.repository.hr.HrBatchMapper.ItemRow;
import com.fasterxml.jackson.databind.*;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;

/** 批次先核实全部最坏工作量，预算引用不可替换；每份各阶段共享同scope。 */
@Service
public class HrBatchBudgetService {
  public record BudgetPlan(
      int maxCalls,
      long maxCost,
      String budgetRef,
      Instant deadline,
      List<String> runRefs,
      String mode,
      String planRef) {
    public BudgetPlan {
      runRefs = List.copyOf(runRefs);
    }
  }

  private final HrBatchBudgetMapper mapper;
  private final HrSemanticGateway gateway;
  private final ObjectMapper json;
  private HrResumeReuseService reuse;
  private HrSensitiveJsonCodec codec;
  private HrBatchLimits limits;

  public HrBatchBudgetService(
      HrBatchBudgetMapper mapper,
      HrSemanticGateway gateway,
      ObjectMapper json,
      HrResumeReuseService reuse,
      HrSensitiveJsonCodec codec) {
    this(mapper, gateway, json, reuse, codec, null);
  }

  @org.springframework.beans.factory.annotation.Autowired
  public HrBatchBudgetService(
      HrBatchBudgetMapper mapper,
      HrSemanticGateway gateway,
      ObjectMapper json,
      HrResumeReuseService reuse,
      HrSensitiveJsonCodec codec,
      HrBatchLimits limits) {
    this(mapper, gateway, json);
    this.reuse = reuse;
    this.codec = codec;
    this.limits = limits;
  }

  public HrBatchBudgetService(
      HrBatchBudgetMapper mapper, HrSemanticGateway gateway, ObjectMapper json) {
    this.mapper = mapper;
    this.gateway = gateway;
    this.json = json;
  }

  public BudgetPlan plan(
      HrActor actor, String batchId, String department, List<ItemRow> items, String mode) {
    HrAccessPolicy.requireFor(actor, "hr:candidate:upload", department, null, "CANDIDATE");
    if (items == null
        || items.isEmpty()
        || items.size() > 100
        || !Set.of("MATCH", "STORE_ONLY").contains(mode))
      throw HrPositionService.invalid("批次预算工作量无效");
    var old = mapper.find(actor.tenantId(), batchId);
    if (old != null) {
      var frozen = decode(old.payload());
      if (!frozen.runRefs().equals(items.stream().map(i -> "hr-import-" + i.id()).toList())
          || !frozen.mode().equals(mode)) throw HrPositionService.conflict();
      return validate(actor, batchId);
    }
    int maximumAttempts = limits == null ? 3 : limits.get(actor, batchId).maxAttempts();
    if (maximumAttempts < 1 || maximumAttempts > 3) throw HrPositionService.invalid("冻结重试上限无效");
    var input = json.createObjectNode();
    var workload = input.putArray("workload");
    List<String> refs = new ArrayList<>();
    for (var item : items) {
      String ref = "hr-import-" + item.id();
      refs.add(ref);
      boolean reusable = false;
      if (reuse != null && item.encryptedContent() != null) {
        try {
          byte[] raw = Base64.getDecoder().decode(codec.open(item.encryptedContent()));
          String hash =
              HexFormat.of()
                  .formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(raw));
          reusable = reuse.find(actor, department, hash, item.filename()) != null;
        } catch (java.security.NoSuchAlgorithmException e) {
          throw new IllegalStateException(e);
        }
      }
      for (int i = 0; i < (reusable ? 0 : 12); i++)
        workload
            .addObject()
            .put("run_ref", ref)
            .put("skill_key", "hr.resume.structure")
            .put("attempts", maximumAttempts);
      if ("MATCH".equals(mode)) {
        for (int i = 0; i < 4; i++)
          workload
              .addObject()
              .put("run_ref", ref)
              .put("skill_key", "hr.requirements.evaluate")
              .put("attempts", maximumAttempts);
        workload
            .addObject()
            .put("run_ref", ref)
            .put("skill_key", "hr.match.explain")
            .put("attempts", maximumAttempts);
      }
    }
    com.fasterxml.jackson.databind.JsonNode checked =
        workload.isEmpty()
            ? json.createObjectNode()
                .put("ready", true)
                .put("budget_ref", "CPU_ONLY")
                .put(
                    "plan_ref",
                    HrPositionService.hash(List.of(actor.tenantId(), batchId, "CPU_ONLY")))
                .put("maximum_calls", 0)
                .put("maximum_cost_microunits", 0)
                .put("deadline_epoch_ms", Instant.now().plusSeconds(600).toEpochMilli())
            : gateway.execute(actor, 6109, "hr-batch-plan-" + batchId, input);
    String budget = checked.path("budget_ref").asText();
    if (!checked.path("ready").asBoolean()
        || budget.isBlank()
        || checked.path("plan_ref").asText().isBlank()
        || !checked.has("deadline_epoch_ms"))
      throw new HrBusinessException("HR_BATCH_BUDGET_REQUIRED", "批次预算未就绪", 409);
    var plan =
        new BudgetPlan(
            checked.path("maximum_calls").isIntegralNumber()
                ? checked.path("maximum_calls").asInt()
                : workload.size() * maximumAttempts,
            checked.path("maximum_cost_microunits").asLong(),
            budget,
            Instant.ofEpochMilli(checked.path("deadline_epoch_ms").asLong()),
            refs,
            mode,
            checked.path("plan_ref").asText());
    try {
      mapper.insert(
          new HrBatchBudgetMapper.Row(
              actor.tenantId(), batchId, department, json.writeValueAsString(plan)));
    } catch (org.springframework.dao.DuplicateKeyException e) {
      throw HrPositionService.conflict();
    } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
      throw new IllegalStateException("HR_BATCH_BUDGET_ENCODING_FAILED");
    }
    return plan;
  }

  public BudgetPlan validate(HrActor actor, String batchId) {
    var row = mapper.find(actor.tenantId(), batchId);
    if (row == null) throw new HrBusinessException("HR_BATCH_BUDGET_REQUIRED", "批次尚未冻结预算", 409);
    HrAccessPolicy.requireFor(actor, "hr:candidate:upload", row.departmentId(), null, "CANDIDATE");
    var plan = decode(row.payload());
    if (plan.planRef() == null || plan.planRef().isBlank())
      throw new HrBusinessException("HR_BATCH_BUDGET_REQUIRED", "批次缺少冻结聚合计划，请重新创建授权批次", 409);
    if (!plan.deadline().isAfter(Instant.now()))
      throw new HrBusinessException("BUDGET_STOPPED", "批次预算已到期", 409);
    if (plan.maxCalls() == 0 && "CPU_ONLY".equals(plan.budgetRef())) return plan;
    var input =
        json.createObjectNode()
            .put("workload_budget_ref", plan.budgetRef())
            .put("workload_plan_ref", plan.planRef());
    var checked = gateway.execute(actor, 6109, "hr-batch-check-" + batchId, input);
    if (!checked.path("ready").asBoolean()
        || !plan.budgetRef().equals(checked.path("budget_ref").asText()))
      throw new HrBusinessException("BUDGET_REFERENCE_CHANGED", "批次预算引用已失效", 409);
    return plan;
  }

  private BudgetPlan decode(String payload) {
    try {
      return json.readValue(payload, BudgetPlan.class);
    } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
      throw new IllegalStateException("HR_BATCH_BUDGET_INVALID");
    }
  }
}

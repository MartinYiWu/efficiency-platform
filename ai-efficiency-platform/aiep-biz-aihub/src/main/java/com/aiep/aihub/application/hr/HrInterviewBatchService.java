package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrInterviewBatchContracts.*;
import com.aiep.aihub.api.hr.HrInterviewContracts.*;
import com.aiep.aihub.repository.hr.HrInterviewBatchMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import org.springframework.stereotype.Service;

@Service
public class HrInterviewBatchService {
  public record FrozenGeneration(GenerationBatch request, String budgetRef, String planRef) {}

  private final HrInterviewBatchMapper mapper;
  private final HrInterviewService interviews;
  private final HrInterviewExportService exports;
  private final HrSemanticGateway gateway;
  private final HrActorAuthority authority;
  private final HrSensitiveJsonCodec codec;
  private final ObjectMapper json;

  public HrInterviewBatchService(
      HrInterviewBatchMapper mapper,
      HrInterviewService interviews,
      HrInterviewExportService exports,
      HrSemanticGateway gateway,
      HrActorAuthority authority,
      HrSensitiveJsonCodec codec,
      ObjectMapper json) {
    this.mapper = mapper;
    this.interviews = interviews;
    this.exports = exports;
    this.gateway = gateway;
    this.authority = authority;
    this.codec = codec;
    this.json = json;
  }

  public Batch generate(HrActor actor, GenerationBatch input, String key) {
    if (!input.confirmed()
        || input.items() == null
        || input.items().isEmpty()
        || input.items().size() > 100) throw HrPositionService.invalid("请确认1至100位候选人的批量范围");
    var replay = replay(actor, key, "interview", input);
    if (replay != null) return replay;
    for (var request : input.items()) interviews.validateGeneration(actor, request);
    String id =
        UUID.nameUUIDFromBytes(
                (actor.tenantId() + ":" + actor.userId() + ":interview:" + key)
                    .getBytes(java.nio.charset.StandardCharsets.UTF_8))
            .toString();
    var plan = json.createObjectNode();
    var workload = plan.putArray("workload");
    for (int i = 0; i < input.items().size(); i++)
      workload
          .addObject()
          .put("run_ref", runRef(id, i))
          .put("skill_key", "hr.interview.generate")
          .put("attempts", 3);
    var budget = gateway.execute(actor, 6109, "hr-interview-plan-" + id, plan);
    Batch batch =
        new Batch(
            id,
            "PENDING",
            input.items().stream()
                .map(r -> new Item(r.candidateId(), "PENDING", null, null, null, null))
                .toList());
    save(
        actor,
        key,
        "interview",
        input,
        new FrozenGeneration(
            input, budget.path("budget_ref").asText(), budget.path("plan_ref").asText()),
        batch);
    Thread.startVirtualThread(
        () ->
            processGeneration(
                actor,
                id,
                input,
                budget.path("budget_ref").asText(),
                budget.path("plan_ref").asText()));
    return batch;
  }

  public Batch export(HrActor actor, ExportBatch input, String key) {
    if (!input.confirmed()
        || input.items() == null
        || input.items().isEmpty()
        || input.items().size() > 100) throw HrPositionService.invalid("请确认1至100份题集的批量导出范围");
    var replay = replay(actor, key, "export", input);
    if (replay != null) return replay;
    String id = UUID.randomUUID().toString();
    Batch batch =
        new Batch(
            id,
            "PENDING",
            input.items().stream()
                .map(r -> new Item(null, "PENDING", r.setId(), null, null, null))
                .toList());
    save(actor, key, "export", input, input, batch);
    Thread.startVirtualThread(() -> processExports(actor, id, input));
    return batch;
  }

  public Batch get(HrActor actor, String id, String kind) {
    var row = mapper.get(actor.tenantId(), id, kind);
    if (row == null || !row.actorId().equals(actor.userId())) throw HrPositionService.missing();
    HrAccessPolicy.require(
        actor, kind.equals("interview") ? "hr:interview:write" : "hr:interview:export");
    var b = read(row.payload(), Batch.class);
    if (kind.equals("interview")) {
      var frozen = read(row.inputJson(), FrozenGeneration.class);
      for (var r : frozen.request().items()) interviews.validateGeneration(actor, r);
    } else {
      for (var r : read(row.inputJson(), ExportBatch.class).items())
        interviews.get(actor, r.setId(), r.setVersion());
    }
    if (row.status().equals("FAILED") && !b.status().equals("FAILED"))
      return new Batch(
          id,
          "FAILED",
          b.items().stream()
              .map(
                  i ->
                      i.status().equals("PENDING")
                          ? new Item(
                              i.candidateId(),
                              "FAILED",
                              i.setId(),
                              i.exportId(),
                              i.grantId(),
                              "HR_RECOVERY_INFLIGHT_UNKNOWN")
                          : i)
              .toList());
    return b;
  }

  private void processGeneration(
      HrActor actor, String id, GenerationBatch input, String budgetRef, String planRef) {
    if (mapper.start(actor.tenantId(), id) != 1) return;
    List<Item> items = new ArrayList<>();
    for (int i = 0; i < input.items().size(); i++) {
      var r = input.items().get(i);
      try {
        var current = authority.refresh(actor);
        var result =
            interviews.generateBound(
                current, r, "batch-" + id + "-" + i, runRef(id, i), budgetRef, planRef);
        items.add(new Item(r.candidateId(), "SUCCEEDED", result.id(), null, null, null));
      } catch (RuntimeException error) {
        String code =
            error instanceof HrBusinessException h ? h.code() : "HR_INTERVIEW_BATCH_FAILED";
        items.add(new Item(r.candidateId(), "FAILED", null, null, null, code));
        if (code.startsWith("PAID_")
            || code.startsWith("BUDGET_")
            || code.startsWith("PROVIDER_")) {
          for (int j = i + 1; j < input.items().size(); j++)
            items.add(
                new Item(input.items().get(j).candidateId(), "FAILED", null, null, null, code));
          break;
        }
      }
      mapper.update(
          actor.tenantId(), id, seal(new Batch(id, "RUNNING", List.copyOf(items))), "RUNNING");
    }
    finish(actor, id, items);
  }

  private void processExports(HrActor actor, String id, ExportBatch input) {
    if (mapper.start(actor.tenantId(), id) != 1) return;
    List<Item> items = new ArrayList<>();
    for (var r : input.items()) {
      try {
        var e = exports.create(authority.refresh(actor), r);
        items.add(new Item(null, "SUCCEEDED", r.setId(), e.id(), e.grantId(), null));
      } catch (RuntimeException error) {
        items.add(
            new Item(
                null,
                "FAILED",
                r.setId(),
                null,
                null,
                error instanceof HrBusinessException h ? h.code() : "HR_EXPORT_BATCH_FAILED"));
      }
    }
    finish(actor, id, items);
  }

  private void finish(HrActor actor, String id, List<Item> items) {
    String state =
        items.stream().allMatch(i -> i.status().equals("SUCCEEDED"))
            ? "SUCCEEDED"
            : "PARTIAL_FAILED";
    mapper.update(actor.tenantId(), id, seal(new Batch(id, state, List.copyOf(items))), state);
  }

  private Batch replay(HrActor actor, String key, String kind, Object input) {
    if (key == null || !key.matches("[A-Za-z0-9_-]{8,100}"))
      throw HrPositionService.invalid("幂等键无效");
    var row = mapper.replay(actor.tenantId(), actor.userId(), key, kind);
    if (row == null) return null;
    if (!row.inputHash().equals(HrPositionService.hash(input))) throw HrPositionService.conflict();
    return get(actor, row.id(), kind);
  }

  private void save(
      HrActor actor, String key, String kind, Object input, Object frozen, Batch batch) {
    mapper.insert(
        new HrInterviewBatchMapper.Row(
            batch.id(),
            actor.tenantId(),
            actor.userId(),
            kind,
            batch.status(),
            seal(batch),
            seal(frozen),
            key,
            HrPositionService.hash(input)));
  }

  private String seal(Object value) {
    try {
      return codec.seal(json.writeValueAsString(value));
    } catch (Exception e) {
      throw new IllegalStateException("HR_BATCH_ENCODING_FAILED");
    }
  }

  private <T> T read(String value, Class<T> type) {
    try {
      return json.readValue(codec.open(value), type);
    } catch (Exception e) {
      throw new IllegalStateException("HR_BATCH_ENCODING_FAILED");
    }
  }

  private static String runRef(String id, int index) {
    return "hr-interview-"
        + UUID.nameUUIDFromBytes(
            (id + ":" + index).getBytes(java.nio.charset.StandardCharsets.UTF_8));
  }

  @org.springframework.context.event.EventListener(
      org.springframework.boot.context.event.ApplicationReadyEvent.class)
  public void recover() {
    mapper.recover();
  }
}

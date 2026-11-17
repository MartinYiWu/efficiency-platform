package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrTalentSemanticContracts.*;
import com.aiep.aihub.repository.hr.*;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;

/** 权限先于检索；每源稳定scope，经统一工作量预检，GET仅重放已存结果。 */
@Service
public class HrTalentSemanticService {
  public record FrozenSource(
      String candidateId,
      String snapshotId,
      String factHash,
      String runRef,
      List<SafeBlock> blocks) {}

  public record SafeBlock(String blockId, String text) {}

  public record FrozenSearch(
      String query, List<FrozenSource> sources, String budgetRef, String planRef) {
    public FrozenSearch(String query, List<FrozenSource> sources, String budgetRef) {
      this(query, sources, budgetRef, null);
    }
  }

  private final HrTalentSemanticMapper jobs;
  private final HrTalentMapper mapper;
  private final HrTalentSearchService talent;
  private final HrSemanticGateway gateway;
  private final HrActorAuthority authority;
  private final HrSensitiveJsonCodec codec;
  private final ObjectMapper json;
  private final org.springframework.transaction.support.TransactionTemplate transactions;

  public HrTalentSemanticService(
      HrTalentSemanticMapper jobs,
      HrTalentMapper mapper,
      HrTalentSearchService talent,
      HrSemanticGateway gateway,
      HrActorAuthority authority,
      HrSensitiveJsonCodec codec,
      ObjectMapper json,
      org.springframework.transaction.PlatformTransactionManager manager) {
    this.jobs = jobs;
    this.mapper = mapper;
    this.talent = talent;
    this.gateway = gateway;
    this.authority = authority;
    this.codec = codec;
    this.json = json;
    this.transactions = new org.springframework.transaction.support.TransactionTemplate(manager);
  }

  public SearchJob create(HrActor actor, SearchRequest request, String key) {
    HrAccessPolicy.require(actor, "hr:candidate:read");
    if (!request.confirmed()
        || request.query() == null
        || request.query().isBlank()
        || request.query().length() > 500
        || key == null
        || !key.matches("[A-Za-z0-9_-]{8,100}")) throw HrTalentSearchService.invalid();
    if (request.query().matches("(?s).*1[3-9][0-9]{9}.*")
        || request.query().contains("@")
        || List.of("婚育", "年龄", "性别", "民族", "宗教", "身份证", "户籍", "残疾").stream()
            .anyMatch(request.query()::contains)) throw HrTalentSearchService.invalid();
    String hash = HrAuditService.hash(write(request));
    var replay = jobs.replay(actor.tenantId(), actor.userId(), key);
    if (replay != null) {
      if (!hash.equals(replay.requestHash())) throw HrCandidateMergeService.conflict();
      return get(actor, replay.id());
    }
    Set<String> requested =
        request.candidateIds() == null ? null : new HashSet<>(request.candidateIds());
    if (requested != null
        && (requested.isEmpty()
            || requested.size() > 20
            || requested.size() != request.candidateIds().size()))
      throw HrTalentSearchService.invalid();
    List<FrozenSource> sources = new ArrayList<>();
    for (var candidate : talent.visibleCandidates(actor, "hr:candidate:read", Instant.now())) {
      if (requested != null && !requested.contains(candidate.id())) continue;
      try {
        talent.purpose(actor, candidate, "TALENT_POOL");
      } catch (HrBusinessException denied) {
        if (requested != null) throw denied;
        continue;
      }
      var facts = talent.facts(actor, candidate);
      List<SafeBlock> blocks = new ArrayList<>();
      int index = 0;
      for (var section : new InterviewViewAssembler().resume(facts)) {
        String text = section.text();
        if (text.length() > 3000)
          throw new HrBusinessException("HR_SEARCH_INPUT_TOO_LARGE", "检索来源过长，须缩小材料范围", 422);
        blocks.add(new SafeBlock("s" + (index++), text));
      }
      if (blocks.isEmpty()) continue;
      if (write(blocks).getBytes(java.nio.charset.StandardCharsets.UTF_8).length > 32000)
        throw new HrBusinessException("HR_SEARCH_INPUT_TOO_LARGE", "单源检索材料过长", 422);
      String factHash = HrAuditService.hash(write(blocks));
      String run =
          "hr-search-"
              + HrAuditService.hash(
                      actor.tenantId()
                          + ":"
                          + request.query()
                          + ":"
                          + candidate.id()
                          + ":"
                          + factHash)
                  .substring(0, 48);
      sources.add(
          new FrozenSource(
              candidate.id(), candidate.currentSnapshotId(), factHash, run, List.copyOf(blocks)));
      if (sources.size() > 20)
        throw new HrBusinessException(
            "HR_SEARCH_SCOPE_TOO_LARGE", "语义检索最多20份授权来源，请先使用结构化条件缩小范围", 422);
    }
    if (requested != null
        && !sources.stream()
            .map(FrozenSource::candidateId)
            .collect(java.util.stream.Collectors.toSet())
            .equals(requested)) throw HrTalentSearchService.missing();
    if (sources.isEmpty())
      throw new HrBusinessException("HR_SEARCH_SOURCE_REQUIRED", "没有可用于人才检索的授权材料", 422);
    String id = UUID.randomUUID().toString();
    Instant now = Instant.now();
    FrozenSearch frozen = new FrozenSearch(request.query(), List.copyOf(sources), null);
    var view = new SearchJob(id, "PREFLIGHT", request.query(), List.of(), now);
    transactions.executeWithoutResult(
        transaction -> {
          jobs.insert(
              new HrTalentSemanticMapper.Row(
                  id,
                  actor.tenantId(),
                  actor.userId(),
                  "PREFLIGHT",
                  seal(frozen),
                  seal(view),
                  key,
                  hash,
                  now,
                  now));
          for (var source : sources) jobs.source(actor.tenantId(), id, source.candidateId());
        });
    try {
      ObjectNode plan = json.createObjectNode();
      var workload = plan.putArray("workload");
      for (var source : sources)
        workload
            .addObject()
            .put("run_ref", source.runRef())
            .put("skill_key", "hr.talent.search")
            .put("attempts", 3);
      var checked = gateway.execute(actor, 6109, "hr-search-plan-" + id, plan);
      String budget = checked.path("budget_ref").asText();
      String planRef = checked.path("plan_ref").asText();
      if (!checked.path("ready").asBoolean() || budget.isBlank() || planRef.isBlank())
        throw new HrBusinessException("HR_SEARCH_BUDGET_REQUIRED", "检索预算预检未通过", 409);
      var ready = new FrozenSearch(frozen.query(), frozen.sources(), budget, planRef);
      var running = new SearchJob(id, "RUNNING", request.query(), List.of(), now);
      if (jobs.update(
              actor.tenantId(),
              id,
              "PREFLIGHT",
              "RUNNING",
              seal(ready),
              seal(running),
              Instant.now())
          != 1) throw HrCandidateMergeService.conflict();
      Thread.startVirtualThread(() -> execute(actor, id, ready, now));
      return running;
    } catch (RuntimeException failure) {
      var failed = new SearchJob(id, "FAILED", request.query(), List.of(), now);
      jobs.update(
          actor.tenantId(), id, "PREFLIGHT", "FAILED", seal(frozen), seal(failed), Instant.now());
      throw failure;
    }
  }

  private void execute(HrActor initial, String id, FrozenSearch frozen, Instant created) {
    List<Hit> hits = new ArrayList<>();
    boolean stopped = false;
    for (var source : frozen.sources()) {
      if (stopped) {
        hits.add(new Hit(source.candidateId(), 0, List.of(), "FAILED", "HR_SEARCH_STOPPED"));
        continue;
      }
      try {
        var actor = authority.refresh(initial);
        authorize(actor, source);
        ObjectNode input =
            json.createObjectNode()
                .put("search_query", frozen.query())
                .put("workload_budget_ref", frozen.budgetRef())
                .put("workload_plan_ref", frozen.planRef());
        ArrayNode blocks = input.putArray("blocks");
        for (var block : source.blocks())
          blocks.addObject().put("block_id", block.blockId()).put("text", block.text());
        JsonNode output = gateway.execute(actor, 6110, source.runRef(), input);
        double relevance = output.path("relevance").asDouble(-1);
        if (relevance < 0
            || relevance > 1
            || !Double.isFinite(relevance)
            || !output.path("matches").isArray()) throw invalidOutput();
        List<Match> matches = new ArrayList<>();
        for (var match : output.path("matches")) {
          String blockId = match.path("block_id").asText();
          String quote = match.path("quote").asText();
          int start = match.path("start").asInt(-1), end = match.path("end").asInt(-1);
          var block =
              source.blocks().stream()
                  .filter(b -> b.blockId().equals(blockId))
                  .findFirst()
                  .orElseThrow(HrTalentSemanticService::invalidOutput);
          int[] points = block.text().codePoints().toArray();
          if (start < 0
              || end <= start
              || end > points.length
              || quote.length() > 1000
              || !new String(points, start, end - start).equals(quote)) throw invalidOutput();
          matches.add(new Match(blockId, start, end, quote));
        }
        if (matches.size() > 5 || relevance > 0 && matches.isEmpty()) throw invalidOutput();
        authorize(authority.refresh(initial), source);
        hits.add(new Hit(source.candidateId(), relevance, List.copyOf(matches), "SUCCEEDED", null));
      } catch (RuntimeException error) {
        String code = error instanceof HrBusinessException h ? h.code() : "HR_SEARCH_FAILED";
        hits.add(new Hit(source.candidateId(), 0, List.of(), "FAILED", code));
        stopped =
            code.startsWith("PAID_") || code.startsWith("BUDGET_") || code.startsWith("PROVIDER_");
      }
    }
    hits.sort(
        Comparator.comparingDouble(Hit::retrievalRelevance)
            .reversed()
            .thenComparing(Hit::candidateId));
    String status =
        hits.stream().allMatch(h -> "SUCCEEDED".equals(h.status()))
            ? "SUCCEEDED"
            : "PARTIAL_FAILED";
    jobs.update(
        initial.tenantId(),
        id,
        "RUNNING",
        status,
        seal(frozen),
        seal(new SearchJob(id, status, frozen.query(), List.copyOf(hits), created)),
        Instant.now());
  }

  public SearchJob get(HrActor actor, String id) {
    var row = jobs.find(actor.tenantId(), id);
    if (row == null || !row.actorId().equals(actor.userId())) throw HrTalentSearchService.missing();
    HrAccessPolicy.require(actor, "hr:candidate:read");
    var frozen = read(row.inputJson(), FrozenSearch.class);
    for (var source : frozen.sources()) authorize(actor, source);
    var view = read(row.resultJson(), SearchJob.class);
    if ("FAILED".equals(row.status()) && !"FAILED".equals(view.status()))
      return new SearchJob(id, "FAILED", view.query(), List.of(), view.createdAt());
    return view;
  }

  private void authorize(HrActor actor, FrozenSource source) {
    var c = talent.authorized(actor, source.candidateId(), "hr:candidate:read");
    talent.purpose(actor, c, "TALENT_POOL");
    if (!source.snapshotId().equals(c.currentSnapshotId()))
      throw new HrBusinessException("HR_SEARCH_FACT_STALE", "检索来源事实已变化，请显式创建新检索", 409);
  }

  @org.springframework.context.event.EventListener(
      org.springframework.boot.context.event.ApplicationReadyEvent.class)
  public void recover() {
    jobs.recover();
  }

  private String write(Object value) {
    try {
      return json.writeValueAsString(value);
    } catch (Exception e) {
      throw new IllegalStateException("HR_SEARCH_ENCODING_FAILED");
    }
  }

  private String seal(Object value) {
    return codec.seal(write(value));
  }

  private <T> T read(String value, Class<T> type) {
    try {
      return json.readValue(codec.open(value), type);
    } catch (Exception e) {
      throw new IllegalStateException("HR_SEARCH_INTEGRITY_FAILED");
    }
  }

  private static HrBusinessException invalidOutput() {
    return new HrBusinessException("HR_SEARCH_CONTRACT_FAILED", "检索相关度或引用校验失败", 422);
  }
}

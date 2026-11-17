package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.api.hr.HrBatchContracts.*;
import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.repository.hr.HrBatchMapper;
import com.aiep.aihub.repository.hr.HrBatchMapper.*;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.Base64;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 授权批次与逐条处理，数据库事务仅保护短状态转换，模型调用始终在事务外。 */
@Service
public class HrBatchService {
  private static final org.slf4j.Logger LOG =
      org.slf4j.LoggerFactory.getLogger(HrBatchService.class);
  private final HrBatchMapper mapper;
  private final HrPositionService positions;
  private final HrCandidateService candidates;
  private final HrMatchingService matching;
  private final HrMatchingRunExecutor matchingExecutor;
  private final HrSensitiveJsonCodec codec;
  private final ObjectMapper json;
  private HrBatchLimits limits;
  private HrReadinessService readiness;
  private HrActorAuthority authority;
  private HrBatchBudgetService budgets;
  private org.springframework.transaction.support.TransactionTemplate transactions;

  @org.springframework.beans.factory.annotation.Autowired
  public HrBatchService(
      HrBatchMapper mapper,
      HrPositionService positions,
      HrCandidateService candidates,
      HrMatchingService matching,
      HrMatchingRunExecutor executor,
      HrSensitiveJsonCodec codec,
      ObjectMapper json,
      HrBatchLimits limits,
      HrReadinessService readiness,
      HrActorAuthority authority,
      HrBatchBudgetService budgets,
      org.springframework.transaction.PlatformTransactionManager manager) {
    this(mapper, positions, candidates, matching, executor, codec, json);
    this.limits = limits;
    this.readiness = readiness;
    this.authority = authority;
    this.budgets = budgets;
    this.transactions = new org.springframework.transaction.support.TransactionTemplate(manager);
  }

  public HrBatchService(
      HrBatchMapper mapper,
      HrPositionService positions,
      HrCandidateService candidates,
      HrMatchingService matching,
      HrMatchingRunExecutor matchingExecutor,
      HrSensitiveJsonCodec codec,
      ObjectMapper json) {
    this.mapper = mapper;
    this.positions = positions;
    this.candidates = candidates;
    this.matching = matching;
    this.matchingExecutor = matchingExecutor;
    this.codec = codec;
    this.json = json;
  }

  public Policy policy(HrActor actor) {
    var row = mapper.latestPolicy(actor.tenantId());
    if (row == null)
      throw new HrBusinessException("HR_POLICY_NOT_READY", "请先由管理员配置并确认招聘材料使用政策", 503);
    try {
      return json.readValue(row.payload(), Policy.class);
    } catch (JsonProcessingException e) {
      throw new IllegalStateException("HR_POLICY_INVALID");
    }
  }

  @Transactional
  public Policy publishPolicy(HrActor actor, Policy input) {
    HrAccessPolicy.require(actor, "hr:settings:edit");
    if (input.authorizationText() == null
        || input.authorizationText().strip().length() < 10
        || input.authorizationText().length() > 5000
        || input.retentionMonths() < 1
        || input.retentionMonths() > 60
        || input.reviewWaitDays() < 1
        || input.reviewWaitDays() > 30
        || input.maximumAttempts() < 1
        || input.maximumAttempts() > 3
        || input.failedRetentionDays() < 1
        || input.failedRetentionDays() > 90
        || input.lowThreshold() < 0
        || input.highThreshold() > 100
        || input.highThreshold() <= input.middleThreshold()
        || input.middleThreshold() <= input.lowThreshold())
      throw HrPositionService.invalid("政策或规则配置无效");
    var old = mapper.latestPolicy(actor.tenantId());
    long current = old == null ? 0 : old.version();
    if (current != input.version()) throw HrPositionService.conflict();
    Policy next =
        new Policy(
            UUID.randomUUID().toString(),
            input.authorizationText().strip(),
            input.retentionMonths(),
            input.reviewWaitDays(),
            input.maximumAttempts(),
            input.failedRetentionDays(),
            input.highThreshold(),
            input.middleThreshold(),
            input.lowThreshold(),
            current + 1);
    mapper.insertPolicy(
        new PolicyRow(next.id(), actor.tenantId(), encode(next), next.version(), Instant.now()));
    return next;
  }

  public UploadPolicy uploadPolicy(HrActor actor) {
    HrAccessPolicy.require(actor, "hr:candidate:upload");
    Policy p = policy(actor);
    com.fasterxml.jackson.databind.JsonNode ready =
        readiness == null ? json.createObjectNode() : readiness.inspect(actor).path("formats");
    List<Format> formats =
        List.of("pdf", "doc", "docx", "jpg", "jpeg", "png", "txt", "md", "html", "zip", "rar", "7z")
            .stream()
            .map(
                s -> {
                  String key = Set.of("jpg", "jpeg", "png").contains(s) ? "image" : s;
                  boolean available =
                      readiness == null
                          ? Set.of("pdf", "docx", "txt", "md", "html", "zip").contains(s)
                          : "available".equals(ready.path(key).asText());
                  return new Format(s, available, available ? null : "本机格式处理依赖尚未就绪");
                })
            .toList();
    return new UploadPolicy(p.id(), p.authorizationText(), formats);
  }

  @Transactional
  public Batch create(HrActor actor, CreateBatch input, String key) {
    HrAccessPolicy.require(actor, "hr:candidate:upload");
    if (!input.authorizationConfirmed()
        || input.maximumItems() < 1
        || input.maximumItems() > 100
        || !Set.of("MATCH", "STORE_ONLY").contains(input.mode()))
      throw HrPositionService.invalid("请确认授权、批次模式及文件数量");
    Policy policy = policy(actor);
    if (!policy.id().equals(input.policyVersionId())) throw HrPositionService.conflict();
    String department = input.departmentId();
    if (input.mode().equals("MATCH")) {
      if (input.positionId() == null) throw HrPositionService.invalid("请选择启用岗位");
      var p = positions.get(actor, input.positionId());
      if (!p.status().equals("ACTIVE")) throw HrPositionService.invalid("岗位尚未启用");
      department = p.departmentId();
    } else if (department == null && actor.departmentIds().size() == 1)
      department = actor.departmentIds().iterator().next();
    HrAccessPolicy.department(actor, department);
    HrAccessPolicy.requireFor(actor, "hr:candidate:upload", department, null, "CANDIDATE");
    if (key == null || !key.matches("[A-Za-z0-9_-]{8,100}"))
      throw HrPositionService.invalid("请提供幂等键");
    String hash = HrPositionService.hash(input);
    var old = mapper.idempotency(actor.tenantId(), key);
    if (old != null) {
      if (!old.requestHash().equals(hash)) throw HrPositionService.conflict();
      return view(actor, old);
    }
    BatchRow row =
        new BatchRow(
            UUID.randomUUID().toString(),
            actor.tenantId(),
            department,
            actor.userId(),
            input.positionId(),
            input.mode(),
            policy.id(),
            input.maximumItems(),
            "DRAFT",
            1,
            Instant.now(),
            key,
            hash);
    mapper.insertBatch(row);
    if (limits != null
        && input.maximumItems() > limits.freeze(actor, department, row.id()).maxBatchItems())
      throw HrPositionService.invalid("批次条目超过当前安全配置");
    return view(actor, row);
  }

  public Batch get(HrActor actor, String id) {
    return view(actor, require(actor, id));
  }

  private BatchRow require(HrActor actor, String id) {
    HrAccessPolicy.require(actor, "hr:candidate:read");
    var row = mapper.batch(actor.tenantId(), id);
    if (row == null) throw HrPositionService.missing();
    HrAccessPolicy.department(actor, row.departmentId());
    HrAccessPolicy.requireFor(actor, "hr:candidate:read", row.departmentId(), null, "CANDIDATE");
    if (actor.authenticated()
        && !row.userId().equals(actor.userId())
        && !HrAccessPolicy.objectIdsFor(actor, "hr:candidate:read", row.departmentId(), "CANDIDATE")
            .contains("*")) throw HrPositionService.missing();
    return row;
  }

  private Batch view(HrActor actor, BatchRow row) {
    var items =
        mapper.items(actor.tenantId(), row.id()).stream()
            .filter(
                item -> {
                  if (item.candidateId() == null) return true;
                  try {
                    candidates.candidate(actor, item.candidateId());
                    return true;
                  } catch (HrBusinessException denied) {
                    if (denied.status() == 404 || denied.status() == 403) return false;
                    throw denied;
                  }
                })
            .map(HrBatchService::itemView)
            .toList();
    return new Batch(
        row.id(),
        row.positionId(),
        row.mode(),
        row.status(),
        row.version(),
        items,
        row.createdAt(),
        (int) items.stream().filter(i -> i.status().equals("COMPLETED")).count(),
        (int) items.stream().filter(i -> i.status().equals("FAILED")).count(),
        (int) items.stream().filter(i -> i.status().equals("NEEDS_REVIEW")).count(),
        items.size());
  }

  @Transactional
  public BatchItem upload(HrActor actor, String id, String filename, byte[] content) {
    HrAccessPolicy.require(actor, "hr:candidate:upload");
    BatchRow batch = mapper.lockBatch(actor.tenantId(), id);
    if (batch == null) throw HrPositionService.missing();
    HrAccessPolicy.department(actor, batch.departmentId());
    HrAccessPolicy.requireFor(
        actor, "hr:candidate:upload", batch.departmentId(), null, "CANDIDATE");
    if (!batch.status().equals("DRAFT")) throw HrPositionService.conflict();
    String name = HrPositionService.text(filename, 255);
    String ext = name.substring(name.lastIndexOf('.') + 1).toLowerCase(Locale.ROOT);
    if (ext.equals("zip")) {
      long archiveMax =
          limits == null ? 100L * 1024 * 1024 : limits.get(actor, id).maxArchiveBytes();
      if (content.length > archiveMax) throw HrPositionService.invalid("压缩包超过本批冻结上限");
      var docs = HrArchiveService.unpack(content);
      if (mapper.items(actor.tenantId(), id).size() + docs.size() > batch.maximumItems())
        throw HrPositionService.invalid("展开后文档数超过批次上限");
      BatchItem first = null;
      for (var doc : docs) {
        var uploaded = upload(actor, id, doc.filename(), doc.content());
        if (first == null) first = uploaded;
      }
      return first;
    }
    if (Set.of("rar", "7z").contains(ext))
      throw new HrBusinessException("HR_FILE_ARCHIVE_PIPELINE_REQUIRED", "请通过压缩包安全上传流程处理", 422);
    if (!Set.of("pdf", "doc", "docx", "jpg", "jpeg", "png", "txt", "md", "html", "zip", "rar", "7z")
        .contains(ext))
      throw new HrBusinessException("HR_FILE_FORMAT_SERVICE_UNAVAILABLE", "此格式的处理依赖尚未就绪", 422);
    boolean archive = Set.of("zip", "rar", "7z").contains(ext);
    long max = archive ? 100L * 1024 * 1024 : 20L * 1024 * 1024;
    if (limits != null) {
      var configured = limits.get(actor, id);
      max = archive ? configured.maxArchiveBytes() : configured.maxFileBytes();
    }
    if (content.length == 0 || content.length > max)
      throw HrPositionService.invalid("文件必须为1字节至20MiB");
    String hash = HrPositionService.hash(Base64.getEncoder().encodeToString(content));
    var items = mapper.items(actor.tenantId(), id);
    var duplicate =
        items.stream().filter(i -> i.contentHash().equals(hash)).findFirst();
    if (duplicate.isPresent()) return itemView(duplicate.get());
    if (items.size() >= batch.maximumItems())
      throw HrPositionService.invalid("批次文件数量达到上限");
    var row =
        new ItemRow(
            UUID.randomUUID().toString(),
            actor.tenantId(),
            id,
            name,
            codec.seal(Base64.getEncoder().encodeToString(content)),
            hash,
            "PENDING",
            "UPLOADED",
            null,
            null,
            0);
    mapper.addItem(row);
    return itemView(row);
  }

  public Batch start(HrActor actor, String id, long expected) {
    HrAccessPolicy.require(actor, "hr:candidate:upload");
    var row = require(actor, id);
    if (mapper.items(actor.tenantId(), id).isEmpty()) throw HrPositionService.invalid("请先上传至少一份材料");
    if (budgets != null)
      budgets.plan(actor, id, row.departmentId(), mapper.items(actor.tenantId(), id), row.mode());
    return transactions == null
        ? startFrozen(actor, id, expected)
        : transactions.execute(status -> startFrozen(actor, id, expected));
  }

  private Batch startFrozen(HrActor actor, String id, long expected) {
    if (mapper.advance(actor.tenantId(), id, expected, "DRAFT", "RUNNING") != 1)
      throw HrPositionService.conflict();
    return get(actor, id);
  }

  public HrBatchBudgetService.BudgetPlan executionPlan(HrActor actor, String id) {
    var row = require(actor, id);
    return budgets.plan(
        actor, id, row.departmentId(), mapper.items(actor.tenantId(), id), row.mode());
  }

  public void process(HrActor originalActor, String id) {
    final HrActor actor = authority == null ? originalActor : authority.refresh(originalActor);
    if (budgets != null) budgets.validate(actor, id);
    BatchRow batch = require(actor, id);
    for (ItemRow item : mapper.items(actor.tenantId(), id)) {
      if (Thread.currentThread().isInterrupted() || !require(actor, id).status().equals("RUNNING"))
        return;
      if (mapper.itemState(
              actor.tenantId(), item.id(), "PENDING", "RUNNING", "EXTRACTING", null, null, 10)
          != 1) continue;
      String candidateId = item.candidateId();
      try {
        Facts facts =
            candidates.importResume(
                actor,
                new ImportResume(
                    batch.departmentId(),
                    item.filename(),
                    codec.open(item.encryptedContent()),
                    true,
                    batch.policyId()),
                "hr-import-" + item.id(),
                () ->
                    !Thread.currentThread().isInterrupted()
                        && require(actor, id).status().equals("RUNNING")
                        && "RUNNING".equals(mapper.item(actor.tenantId(), item.id()).status()));
        candidateId = facts.candidateId();
        if (mapper.itemState(
                actor.tenantId(),
                item.id(),
                "RUNNING",
                "RUNNING",
                "STRUCTURED",
                candidateId,
                null,
                70)
            != 1) continue;
        if (!require(actor, id).status().equals("RUNNING")) {
          mapper.itemState(
              actor.tenantId(),
              item.id(),
              "RUNNING",
              "CANCELLED",
              "CANCELLED",
              facts.candidateId(),
              null,
              100);
          return;
        }
        boolean hardReview =
            batch.mode().equals("MATCH")
                && HrQualityPolicy.weakHardFacts(
                        facts.fields(),
                        positions
                            .config(
                                actor,
                                batch.positionId(),
                                positions.get(actor, batch.positionId()).configVersion())
                            .snapshot()
                            .hardConditions())
                    >= 2;
        if (batch.mode().equals("MATCH") && facts.status().equals("CONFIRMED") && !hardReview) {
          MatchRequest match =
              new MatchRequest(facts.candidateId(), batch.positionId(), facts.version());
          var run =
              matching.prepareBound(
                  actor,
                  match,
                  "batch-" + item.id() + "-" + item.contentHash().substring(0, 12),
                  "hr-import-" + item.id());
          if (!require(actor, id).status().equals("RUNNING")
              || !"RUNNING".equals(mapper.item(actor.tenantId(), item.id()).status())) {
            cancelMatchingScope(actor, item.id());
            continue;
          }
          matching.execute(actor, match, run.id());
        }
        mapper.itemState(
            actor.tenantId(),
            item.id(),
            "RUNNING",
            facts.status().equals("CONFIRMED") && !hardReview ? "COMPLETED" : "NEEDS_REVIEW",
            "STRUCTURED",
            facts.candidateId(),
            null,
            100);
      } catch (RuntimeException error) {
        String location =
            java.util.Arrays.stream(error.getStackTrace())
                .filter(frame -> frame.getClassName().startsWith("com.aiep."))
                .findFirst()
                .map(frame -> frame.getClassName() + ":" + frame.getLineNumber())
                .orElse("external");
        LOG.warn(
            "event=hr_batch_item_failed causeType={} location={}",
            error.getClass().getSimpleName(),
            location);
        String code =
            error instanceof HrBusinessException b ? b.code() : "HR_FILE_PROCESSING_FAILED";
        mapper.itemState(
            actor.tenantId(), item.id(), "RUNNING", "FAILED", "FAILED", candidateId, code, 100);
        if (code.startsWith("PAID_")
            || code.startsWith("BUDGET_")
            || code.startsWith("WORKLOAD_") || code.startsWith("LEDGER_") || java.util.Set.of("UNKNOWN_PRICE","INVALID_PRICE","INVALID_PLAN").contains(code)
              || code.startsWith("AGENT_")
            || code.equals("NO_BUDGET")
            || code.equals("PROVIDER_PAYMENT_REQUIRED")) {
          mapper.block(actor.tenantId(), id);
          return;
        }
      }
    }
    mapper.finish(actor.tenantId(), id);
  }

  public Batch cancel(HrActor actor, String id) {
    HrAccessPolicy.require(actor, "hr:candidate:upload");
    var batch = require(actor, id);
    HrAccessPolicy.requireFor(
        actor, "hr:candidate:upload", batch.departmentId(), null, "CANDIDATE");
    mapper.cancel(actor.tenantId(), id);
    for (var item : mapper.items(actor.tenantId(), id)) {
      mapper.itemState(
          actor.tenantId(), item.id(), "PENDING", "CANCELLED", "CANCELLED", null, null, 100);
      if (item.status().equals("RUNNING")) {
        mapper.itemState(
            actor.tenantId(), item.id(), "RUNNING", "CANCELLED", "CANCELLED", null, null, 100);
        if (!cancelMatchingScope(actor, item.id())) {
          mapper.itemState(
              actor.tenantId(),
              item.id(),
              "CANCELLED",
              "CANCEL_PENDING",
              "CANCEL_PENDING",
              null,
              "HR_CANCEL_NOT_CONFIRMED",
              100);
          mapper.pendingCancel(actor.tenantId(), id);
        }
      }
    }
    return get(actor, id);
  }

  public BatchItem cancelItem(HrActor actor, String id) {
    var item = mapper.item(actor.tenantId(), id);
    if (item == null) throw HrPositionService.missing();
    var batch = require(actor, item.batchId());
    HrAccessPolicy.requireFor(
        actor, "hr:candidate:upload", batch.departmentId(), null, "CANDIDATE");
    HrAccessPolicy.require(actor, "hr:candidate:upload");
    mapper.itemState(actor.tenantId(), id, "PENDING", "CANCELLED", "CANCELLED", null, null, 100);
    mapper.itemState(actor.tenantId(), id, "RUNNING", "CANCELLED", "CANCELLED", null, null, 100);
    if (item.status().equals("RUNNING") && !cancelMatchingScope(actor, id)) {
      mapper.itemState(
          actor.tenantId(),
          id,
          "CANCELLED",
          "CANCEL_PENDING",
          "CANCEL_PENDING",
          null,
          "HR_CANCEL_NOT_CONFIRMED",
          100);
    }
    return itemView(mapper.item(actor.tenantId(), id));
  }

  private boolean cancelMatchingScope(HrActor actor, String itemId) {
    String scope = "hr-import-" + itemId;
    matching.cancelBatchScope(actor.tenantId(), scope);
    boolean confirmed = candidates.cancelImport(actor, scope);
    if (confirmed) matching.confirmBatchScopeCancellation(actor.tenantId(), scope);
    return confirmed;
  }

  public RunResponse continueCandidate(
      HrActor actor, String candidateId, long expectedVersion, String key) {
    var source = mapper.candidateBatch(actor.tenantId(), candidateId);
    if (source == null || source.positionId() == null)
      throw new HrBusinessException("HR_POSITION_REQUIRED", "请为候选人选择目标岗位", 422);
    HrAccessPolicy.department(actor, source.departmentId());
    if (budgets != null) budgets.validate(actor, source.id());
    MatchRequest request = new MatchRequest(candidateId, source.positionId(), expectedVersion);
    var item = mapper.candidateItem(actor.tenantId(), candidateId);
    if (item == null) throw HrPositionService.missing();
    var run = matching.prepareBound(actor, request, key, "hr-import-" + item.id());
    matchingExecutor.submit(actor, request, run);
    return new RunResponse(run.id(), run.status());
  }

  private static BatchItem itemView(ItemRow row) {
    return new BatchItem(
        row.id(),
        row.filename(),
        row.status(),
        row.stage(),
        row.candidateId(),
        row.errorCode(),
        row.errorCode() == null ? null : "本条处理未完成，请核对配置和材料后重试",
        row.progress(),
        row.contentHash());
  }

  private String encode(Object value) {
    try {
      return json.writeValueAsString(value);
    } catch (JsonProcessingException e) {
      throw new IllegalStateException("HR_POLICY_INVALID");
    }
  }
}


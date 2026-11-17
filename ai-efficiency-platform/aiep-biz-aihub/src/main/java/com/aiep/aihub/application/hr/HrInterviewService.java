package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrInterviewContracts.*;
import com.aiep.aihub.repository.hr.HrTalentMapper;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

/** 模型仅生成题目，Java校验时长、来源、禁用内容并保存不可变题集版本。 */
@Service
public class HrInterviewService {
  private final HrActorAuthority authority;
  private final HrInterviewTemplateService templates;
  private final HrTalentMapper mapper;
  private final HrTalentSearchService talent;
  private final HrPositionService positions;
  private final HrSemanticGateway gateway;
  private final ObjectMapper json;
  private final HrSensitiveJsonCodec codec;
  private final HrAuditService audit;
  private final TransactionTemplate tx;
  private final org.springframework.beans.factory.ObjectProvider<HrInterviewBindingPort> bindings;
  private static final List<String> FORBIDDEN =
      List.of(
          "婚姻", "婚育", "生育", "怀孕", "民族", "宗教", "政治面貌", "身份证", "性取向", "健康状况", "年龄", "性别", "户籍", "照片",
          "残疾", "AI认为", "评分低", "需警惕", "总分", "匹配分", "评分", "评级", "档位", "排名", "强中弱");

  public HrInterviewService(
      HrActorAuthority authority,
      HrInterviewTemplateService templates,
      HrTalentMapper mapper,
      HrTalentSearchService talent,
      HrPositionService positions,
      HrSemanticGateway gateway,
      ObjectMapper json,
      HrSensitiveJsonCodec codec,
      HrAuditService audit,
      org.springframework.transaction.PlatformTransactionManager transactions,
      org.springframework.beans.factory.ObjectProvider<HrInterviewBindingPort> bindings) {
    this.authority = authority;
    this.templates = templates;
    this.bindings = bindings;
    this.mapper = mapper;
    this.talent = talent;
    this.positions = positions;
    this.gateway = gateway;
    this.json = json;
    this.codec = codec;
    this.audit = audit;
    this.tx = new TransactionTemplate(transactions);
  }

  private record Prepared(
      com.aiep.aihub.api.hr.HrCandidateContracts.Candidate candidate,
      HrPositionContracts.Position position,
      HrPositionContracts.ConfigVersion config,
      Template template,
      int[] counts,
      int[] durations) {}

  public void validateGeneration(HrActor actor, GenerateRequest request) {
    prepare(actor, request);
  }

  private Prepared prepare(HrActor actor, GenerateRequest request) {
    HrAccessPolicy.require(actor, "hr:interview:write");
    var c = talent.authorized(actor, request.candidateId(), "hr:candidate:read");
    HrAccessPolicy.requireFor(actor, "hr:interview:write", c.departmentId(), c.id(), "CANDIDATE");
    talent.purpose(actor, c, "INTERVIEW");
    if (c.version() != request.expectedCandidateVersion()) throw HrCandidateMergeService.conflict();
    var position = positions.get(actor, request.positionId());
    var config =
        positions.withCurrentContext(
            actor, position, positions.config(actor, position.id(), position.configVersion()));
    Template template =
        request.templateId() == null || request.templateId().isBlank()
            ? null
            : templates.published(actor, request.templateId(), request.templateVersion());
    int[] counts =
        request.counts() != null
            ? request.counts().stream().mapToInt(Integer::intValue).toArray()
            : template != null
                ? template.counts().stream().mapToInt(Integer::intValue).toArray()
                : HrInterviewRules.preset(request.targetMinutes());
    int[] durations =
        request.durations() != null
            ? request.durations().stream().mapToInt(Integer::intValue).toArray()
            : template != null
                ? template.durations().stream().mapToInt(Integer::intValue).toArray()
                : new int[] {3, 3, 3, 4, 4, 3};
    int estimated = HrInterviewRules.estimated(counts, durations);
    if (estimated > request.targetMinutes() || request.targetMinutes() > 600)
      throw HrTalentSearchService.invalid();
    return new Prepared(c, position, config, template, counts, durations);
  }

  public InterviewSet generate(HrActor actor, GenerateRequest request, String key) {
    return generateBound(actor, request, key, null, null);
  }

  public InterviewSet generateBound(
      HrActor actor, GenerateRequest request, String key, String stableRunRef, String budgetRef) {
    return generateBound(actor, request, key, stableRunRef, budgetRef, null);
  }

  public InterviewSet generateBound(
      HrActor actor,
      GenerateRequest request,
      String key,
      String stableRunRef,
      String budgetRef,
      String planRef) {
    var prepared = prepare(actor, request);
    var c = prepared.candidate();
    var facts = talent.facts(actor, c);
    var position = prepared.position();
    var config = prepared.config();
    Template template = prepared.template();
    int[] counts = prepared.counts(), durations = prepared.durations();
    HrInterviewBindingPort bindingPort = bindings.getIfAvailable();
    if (bindingPort == null)
      throw new HrBusinessException("HR_MODEL_BINDING_NOT_READY", "面试生成绑定版本未就绪", 503);
    var binding = bindingPort.resolve(actor);
    String cache =
        HrAuditService.hash(
            write(
                List.of(
                    actor.tenantId(),
                    new TreeSet<>(actor.departmentIds()),
                    new TreeSet<>(actor.candidateIds()),
                    Objects.toString(request.templateId(), ""),
                    Objects.toString(request.templateVersion(), ""),
                    template == null ? "" : HrAuditService.hash(write(template)),
                    config.snapshotHash(),
                    HrAuditService.hash(write(config.bindings())),
                    position.contextVersion(),
                    Objects.toString(request.round(), ""),
                    Objects.toString(request.language(), "zh"),
                    request.targetMinutes(),
                    counts,
                    durations,
                    c.id(),
                    c.currentSnapshotId(),
                    binding.promptVersion(),
                    binding.modelRouteVersion())));
    String inputHash = HrAuditService.hash(write(request));
    String replay = operation(actor, "interview", key, inputHash);
    if (replay != null) {
      if (mapper.set(actor.tenantId(), replay, null) == null)
        throw new HrBusinessException(
            "HR_INTERVIEW_OPERATION_PENDING", "操作已经提交，不能重复生成；请检查原任务状态", 409);
      return get(actor, replay, null);
    }
    var cached = mapper.cached(actor.tenantId(), cache);
    if (cached != null && cached.candidateId().equals(c.id())) {
      var result = get(actor, cached.id(), cached.version());
      tx.executeWithoutResult(
          status ->
              mapper.insertOperation(
                  actor.tenantId(), actor.userId(), "interview", key, inputHash, result.id()));
      return result;
    }
    ObjectNode input = json.createObjectNode();
    input.put("candidate_ref", c.id());
    input.put(
        "jd_text",
        Objects.toString(
                config.context() == null ? config.snapshot().jdText() : config.context().jdText(),
                "")
            + (template == null
                ? ""
                : "\n面试模板（仅约束题型，不是候选人事实）：" + write(template.layerInstructions())));
    input.set("facts", json.valueToTree(facts.structuredFacts()));
    addEvidenceBlocks(input, facts);
    if (config.bindings() != null && !config.bindings().isEmpty())
      input.set("expected_bindings", json.valueToTree(config.bindings()));
    ArrayNode requirements = input.putArray("requirements");
    for (var criterion : config.snapshot().criteria()) {
      ObjectNode r = requirements.addObject();
      r.put("requirement_id", criterion.id());
      r.put("criterion", criterion.criterion());
    }
    ObjectNode plan = input.putObject("interview");
    plan.put("target_minutes", request.targetMinutes());
    plan.set("counts", json.valueToTree(counts));
    plan.set("durations", json.valueToTree(durations));
    String id = UUID.randomUUID().toString();
    var pending =
        new InterviewSet(
            id,
            c.id(),
            position.id(),
            1,
            "GENERATING",
            request.targetMinutes(),
            0,
            List.of(),
            List.of(),
            Instant.now());
    tx.executeWithoutResult(
        status -> {
          mapper.insertOperation(actor.tenantId(), actor.userId(), "interview", key, inputHash, id);
          save(actor, pending, write(List.of(c.id())), cache);
          mapper.freezeGeneration(
              actor.tenantId(), id, codec.seal(write(config)), write(List.of(c.id())));
        });
    try {
      String runRef = stableRunRef == null ? "hr-interview-" + id : stableRunRef;
      if (planRef == null) {
        var checked = preflight(actor, runRef);
        input.put("workload_budget_ref", checked.path("budget_ref").asText());
        input.put("workload_plan_ref", checked.path("plan_ref").asText());
      } else {
        if (budgetRef == null) throw HrTalentSearchService.invalid();
        input.put("workload_budget_ref", budgetRef);
        input.put("workload_plan_ref", planRef);
      }
      JsonNode output = gateway.execute(actor, 6105, runRef, input);
      List<Question> questions = readQuestions(output);
      Set<String> known = new HashSet<>();
      facts.structuredFacts().forEach(f -> known.add(f.factId()));
      config.snapshot().criteria().forEach(r -> known.add(r.id()));
      validate(questions, known, request.targetMinutes());
      List<Integer> unfilled = new ArrayList<>();
      for (JsonNode n : output.path("unfilled")) unfilled.add(n.asInt() - 1);
      for (int i = 0; i < 6; i++) {
        final int layer = i;
        long actual = questions.stream().filter(q -> q.layer() == layer).count();
        if (actual > counts[i] || (actual < counts[i] && !unfilled.contains(i))) throw contract();
      }
      var set =
          new InterviewSet(
              id,
              c.id(),
              position.id(),
              2,
              "READY",
              request.targetMinutes(),
              questions.stream().mapToInt(Question::minutes).sum(),
              questions,
              List.copyOf(unfilled),
              Instant.now(),
              new InterviewViewAssembler().resume(facts));
      return tx.execute(
          status -> {
            var currentActor = authority.refresh(actor);
            talent.authorized(currentActor, c.id(), "hr:candidate:read");
            HrAccessPolicy.requireFor(
                currentActor, "hr:interview:write", c.departmentId(), c.id(), "CANDIDATE");
            if (mapper.candidate(actor.tenantId(), c.id()).version() != c.version())
              throw HrCandidateMergeService.conflict();
            save(actor, set, write(List.of(c.id())), cache);
            audit.append(actor, "INTERVIEW_GENERATED", id, c.departmentId());
            return set;
          });
    } catch (RuntimeException failure) {
      var failed =
          new InterviewSet(
              id,
              c.id(),
              position.id(),
              2,
              "FAILED",
              request.targetMinutes(),
              0,
              List.of(),
              List.of(),
              Instant.now());
      tx.executeWithoutResult(
          status -> {
            var row = mapper.set(actor.tenantId(), id, null);
            if (row != null && row.version() == 1)
              save(actor, failed, write(List.of(c.id())), cache);
          });
      throw failure;
    }
  }

  public InterviewSet get(HrActor actor, String id, Long version) {
    HrAccessPolicy.require(actor, "hr:interview:read");
    var row = mapper.set(actor.tenantId(), id, version);
    if (row == null) throw HrTalentSearchService.missing();
    positions.get(actor, row.positionId());
    authorizeProvenance(actor, row);
    var candidate = talent.authorized(actor, row.candidateId(), "hr:candidate:read");
    HrAccessPolicy.requireFor(
        actor, "hr:interview:read", candidate.departmentId(), candidate.id(), "CANDIDATE");
    return decode(row);
  }

  public List<InterviewSet> list(HrActor actor, String candidate) {
    talent.authorized(actor, candidate, "hr:candidate:read");
    HrAccessPolicy.require(actor, "hr:interview:read");
    var departments = HrAccessPolicy.departmentsFor(actor, "hr:position:read");
    if (departments.isEmpty() || actor.positionIds().isEmpty()) return List.of();
    return mapper
        .setsVisible(
            actor.tenantId(),
            candidate,
            departments,
            actor.positionIds(),
            actor.authenticated() ? actor.grants() : List.of())
        .stream()
        .map(r -> get(actor, r.id(), r.version()))
        .toList();
  }

  public InterviewSet edit(HrActor actor, String id, EditRequest request) {
    HrAccessPolicy.require(actor, "hr:interview:write");
    var old = get(actor, id, null);
    if (!"READY".equals(old.status())) throw HrCandidateMergeService.conflict();
    if (old.version() != request.expectedVersion()) throw HrCandidateMergeService.conflict();
    var c = talent.authorized(actor, old.candidateId(), "hr:candidate:read");
    HrAccessPolicy.requireFor(actor, "hr:interview:write", c.departmentId(), c.id(), "CANDIDATE");
    var config = frozenConfig(actor, old);
    Set<String> known = new HashSet<>();
    talent.facts(actor, c).structuredFacts().forEach(f -> known.add(f.factId()));
    config.snapshot().criteria().forEach(r -> known.add(r.id()));
    validate(request.questions(), known, old.targetMinutes());
    var next =
        new InterviewSet(
            id,
            old.candidateId(),
            old.positionId(),
            old.version() + 1,
            "READY",
            old.targetMinutes(),
            request.questions().stream().mapToInt(Question::minutes).sum(),
            List.copyOf(request.questions()),
            List.of(),
            Instant.now(),
            old.resumeSections());
    return tx.execute(
        status -> {
          var current = mapper.set(actor.tenantId(), id, null);
          if (current.version() != old.version()) throw HrCandidateMergeService.conflict();
          save(actor, next, current.provenance(), HrAuditService.hash(write(next)));
          audit.append(actor, "INTERVIEW_EDITED", id, c.departmentId());
          return next;
        });
  }

  public InterviewSet regenerate(
      HrActor actor, String id, String questionId, RegenerationRequest request) {
    var old = get(actor, id, null);
    if (!"READY".equals(old.status())) throw HrCandidateMergeService.conflict();
    if (old.version() != request.expectedVersion()) throw HrCandidateMergeService.conflict();
    Question selected =
        old.questions().stream()
            .filter(q -> q.id().equals(questionId))
            .findFirst()
            .orElseThrow(HrTalentSearchService::missing);
    var c = talent.authorized(actor, old.candidateId(), "hr:candidate:read");
    HrAccessPolicy.require(actor, "hr:interview:write");
    talent.purpose(actor, c, "INTERVIEW");
    ObjectNode input = json.createObjectNode();
    input.put("candidate_ref", c.id());
    input.set("facts", json.valueToTree(talent.facts(actor, c).structuredFacts()));
    addEvidenceBlocks(input, talent.facts(actor, c));
    HrAccessPolicy.requireFor(actor, "hr:interview:write", c.departmentId(), c.id(), "CANDIDATE");
    var config = frozenConfig(actor, old);
    input.put(
        "jd_text",
        Objects.toString(
                config.context() == null ? config.snapshot().jdText() : config.context().jdText(),
                "")
            + "\n仅再生当前题的相同目的与维度："
            + selected.purpose()
            + "；"
            + selected.dimension());
    if (config.bindings() != null && !config.bindings().isEmpty())
      input.set("expected_bindings", json.valueToTree(config.bindings()));
    ArrayNode rs = input.putArray("requirements");
    for (var criterion : config.snapshot().criteria()) {
      var r = rs.addObject();
      r.put("requirement_id", criterion.id());
      r.put("criterion", criterion.criterion());
    }
    int[] counts = new int[6];
    counts[selected.layer()] = 1;
    int[] durations = {3, 3, 3, 4, 4, 3};
    durations[selected.layer()] = selected.minutes();
    var plan = input.putObject("interview");
    plan.put("target_minutes", selected.minutes());
    plan.set("counts", json.valueToTree(counts));
    plan.set("durations", json.valueToTree(durations));
    String regenerationHash = HrAuditService.hash(write(List.of(id, questionId, old.version())));
    String regenerationKey = HrAuditService.hash(id + ":" + old.version() + ":" + questionId);
    String prior = operation(actor, "interview-regenerate", regenerationKey, regenerationHash);
    if (prior != null)
      throw new HrBusinessException(
          "HR_INTERVIEW_REGENERATION_ALREADY_SUBMITTED", "此版本单题再生已提交，请读取题集状态，不重复收费", 409);
    String regenerationRun =
        "hr-interview-"
            + UUID.nameUUIDFromBytes(
                (actor.tenantId() + ":" + regenerationKey)
                    .getBytes(java.nio.charset.StandardCharsets.UTF_8));
    tx.executeWithoutResult(
        status ->
            mapper.insertOperation(
                actor.tenantId(),
                actor.userId(),
                "interview-regenerate",
                regenerationKey,
                regenerationHash,
                regenerationRun));
    var checked = preflight(actor, regenerationRun);
    input.put("workload_budget_ref", checked.path("budget_ref").asText());
    input.put("workload_plan_ref", checked.path("plan_ref").asText());
    var generated = readQuestions(gateway.execute(actor, 6105, regenerationRun, input));
    if (generated.size() != 1 || generated.getFirst().layer() != selected.layer()) throw contract();
    Question q = generated.getFirst();
    Question replacement =
        new Question(
            selected.id(),
            q.layer(),
            q.title(),
            q.purpose(),
            q.answerPoints(),
            q.followUps(),
            q.references(),
            q.sourceType(),
            q.sourceIds(),
            q.minutes(),
            q.dimension());
    var changed =
        old.questions().stream()
            .map(existing -> existing.id().equals(questionId) ? replacement : existing)
            .toList();
    return edit(authority.refresh(actor), id, new EditRequest(old.version(), changed));
  }

  public void authorizeProvenance(HrActor actor, HrTalentMapper.SetRow row) {
    try {
      List<String> sources =
          json.readValue(
              row.provenance(),
              json.getTypeFactory().constructCollectionType(List.class, String.class));
      for (String source : sources) {
        var c = talent.authorized(actor, source, "hr:candidate:read");
        talent.purpose(actor, c, "INTERVIEW");
      }
    } catch (HrBusinessException e) {
      throw e;
    } catch (Exception e) {
      throw contract();
    }
  }

  private HrPositionContracts.ConfigVersion frozenConfig(HrActor actor, InterviewSet set) {
    positions.get(actor, set.positionId());
    String sealed = mapper.generationConfig(actor.tenantId(), set.id());
    if (sealed == null)
      throw new HrBusinessException(
          "HR_INTERVIEW_SNAPSHOT_REQUIRED", "历史题集缺少生成配置快照，不能按最新规则替代", 409);
    try {
      return json.readValue(codec.open(sealed), HrPositionContracts.ConfigVersion.class);
    } catch (HrBusinessException e) {
      throw e;
    } catch (Exception e) {
      throw contract();
    }
  }

  public void requireLiveProvenance(HrTalentMapper.SetRow row) {
    try {
      List<String> sources =
          json.readValue(
              row.provenance(),
              json.getTypeFactory().constructCollectionType(List.class, String.class));
      if (sources.isEmpty()) throw HrTalentSearchService.missing();
      for (String id : sources) {
        talent.liveUse(row.tenantId(), id, "INTERVIEW");
        var c = mapper.candidate(row.tenantId(), id);
        if (c == null
            || !"ACTIVE".equals(c.status())
            || c.expiresAt() == null
            || !c.expiresAt().isAfter(Instant.now())) throw HrTalentSearchService.missing();
      }
    } catch (HrBusinessException e) {
      throw e;
    } catch (Exception e) {
      throw contract();
    }
  }

  public InterviewSet decode(HrTalentMapper.SetRow row) {
    try {
      var set = json.readValue(codec.open(row.payload()), InterviewSet.class);
      return new InterviewSet(
          set.id(),
          set.candidateId(),
          set.positionId(),
          set.version(),
          row.status(),
          set.targetMinutes(),
          set.estimatedMinutes(),
          set.questions(),
          set.insufficientLayers(),
          set.createdAt(),
          set.resumeSections());
    } catch (HrBusinessException e) {
      throw e;
    } catch (Exception e) {
      throw contract();
    }
  }

  private void save(HrActor actor, InterviewSet set, String provenance, String cache) {
    mapper.insertSet(
        new HrTalentMapper.SetRow(
            set.id(),
            actor.tenantId(),
            set.candidateId(),
            set.positionId(),
            set.version(),
            set.status(),
            codec.seal(write(set)),
            provenance,
            cache,
            actor.userId(),
            set.createdAt()));
  }

  private String operation(HrActor actor, String route, String key, String hash) {
    if (key == null || key.isBlank() || key.length() > 100) throw HrTalentSearchService.invalid();
    String result = mapper.operation(actor.tenantId(), actor.userId(), route, key, hash);
    if ("!CONFLICT".equals(result)) throw HrCandidateMergeService.conflict();
    return result;
  }

  private List<Question> readQuestions(JsonNode output) {
    List<Question> questions = new ArrayList<>();
    for (JsonNode q : output.path("questions")) {
      List<String> points = new ArrayList<>(),
          follow = new ArrayList<>(),
          source = new ArrayList<>();
      q.path("answer_points").forEach(n -> points.add(n.asText()));
      q.path("followups").forEach(n -> follow.add(n.asText()));
      q.path("source_ids").forEach(n -> source.add(n.asText()));
      int layer = q.path("layer").asInt() - 1;
      questions.add(
          new Question(
              q.path("question_id").asText(),
              layer,
              q.path("text").asText(),
              q.path("purpose").asText(),
              points,
              follow,
              new Reference(
                  q.path("excellent").asText(),
                  q.path("qualified").asText(),
                  q.path("needs_verification").asText()),
              layer < 3 ? "RESUME_VERIFY" : "REQUIREMENT",
              source,
              q.path("minutes").asInt(),
              q.path("dimension").asText()));
    }
    return List.copyOf(questions);
  }

  public void validate(List<Question> questions, Set<String> known, int target) {
    if (questions == null || questions.size() > 40) throw contract();
    Set<String> ids = new HashSet<>();
    int total = 0;
    for (Question q : questions) {
      if (q == null
          || q.id() == null
          || q.id().isBlank()
          || q.id().length() > 100
          || !ids.add(q.id())
          || q.layer() < 0
          || q.layer() > 5
          || q.minutes() < 1
          || q.minutes() > 15
          || q.title() == null
          || q.title().isBlank()
          || q.title().length() > 1000
          || q.purpose() == null
          || q.purpose().isBlank()
          || q.purpose().length() > 300
          || q.answerPoints() == null
          || q.answerPoints().size() < 3
          || q.answerPoints().size() > 5
          || q.followUps() == null
          || q.followUps().size() < 2
          || q.followUps().size() > 3
          || q.references() == null
          || !validAnswer(q.references().excellent(), 1000)
          || !validAnswer(q.references().qualified(), 1000)
          || !validAnswer(q.references().needsVerification(), 1000)
          || q.answerPoints().stream().anyMatch(value -> !validAnswer(value, 1000))
          || q.followUps().stream().anyMatch(value -> !validAnswer(value, 1000))
          || !validAnswer(q.dimension(), 100)
          || q.sourceIds() == null
          || q.sourceIds().size() > 5
          || !known.containsAll(q.sourceIds())
          || (q.layer() < 3 && q.sourceIds().isEmpty())
          || !Set.of("RESUME_VERIFY", "REQUIREMENT").contains(q.sourceType())) throw contract();
      String content = write(q);
      HrProtectedAttributes.validateRule(content);
      if (FORBIDDEN.stream().anyMatch(content::contains)
          || content.matches("(?s).*\\b[\\w.+-]+@[\\w.-]+\\.[A-Za-z]{2,}\\b.*")
          || content.matches("(?s).*1[3-9][0-9]{9}.*")) throw contract();
      total += q.minutes();
    }
    if (total > target) throw contract();
  }

  private boolean validAnswer(String value, int limit) {
    return value != null && !value.isBlank() && value.length() <= limit;
  }

  private static void addEvidenceBlocks(ObjectNode input, HrCandidateContracts.Facts facts) {
    Set<String> ids = new HashSet<>();
    facts.structuredFacts().forEach(f -> f.evidence().forEach(e -> ids.add(e.blockId())));
    var blocks = input.putArray("blocks");
    for (var block : facts.blocks())
      if (ids.contains(block.id())) {
        var value = blocks.addObject().put("block_id", block.id()).put("text", block.text());
        if (block.page() != null) value.put("page", block.page());
      }
  }

  private JsonNode preflight(HrActor actor, String runRef) {
    var request = json.createObjectNode();
    request
        .putArray("workload")
        .addObject()
        .put("run_ref", runRef)
        .put("skill_key", "hr.interview.generate")
        .put("attempts", 3);
    var checked =
        gateway.execute(
            actor,
            6109,
            "hr-interview-plan-" + HrAuditService.hash(runRef).substring(0, 40),
            request);
    if (!checked.path("ready").asBoolean()
        || checked.path("budget_ref").asText().isBlank()
        || checked.path("plan_ref").asText().isBlank())
      throw new HrBusinessException("HR_INTERVIEW_BUDGET_REQUIRED", "面试生成预算计划未就绪", 409);
    return checked;
  }

  private String write(Object value) {
    try {
      return json.writeValueAsString(value);
    } catch (Exception e) {
      throw contract();
    }
  }

  private static HrBusinessException contract() {
    return new HrBusinessException("HR_INTERVIEW_CONTRACT_FAILED", "题目结构、来源或安全校验失败", 422);
  }
}

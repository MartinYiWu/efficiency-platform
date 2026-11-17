package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.repository.hr.HrBatchMapper;
import com.fasterxml.jackson.databind.*;
import java.time.Instant;
import java.util.*;
import java.util.function.BooleanSupplier;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class HrCandidateService {
  private final HrCandidateRepositoryPort repository;
  private final ObjectMapper json;
  private final HrSensitiveJsonCodec codec;
  private final HrSemanticGateway gateway;
  private final HrBatchMapper batches;
  private HrSourceAuthorization sources;
  private com.aiep.platformfile.api.PrivateFileFacade files;
  private HrFactChangeService factChanges;
  private HrDictionaryService dictionary;
  private org.springframework.transaction.support.TransactionTemplate transactions;
  private HrIdentityAssociationService associations;
  private HrFactNormalization normalization;
  private HrResumeReuseService reuse;
  private com.aiep.aihub.repository.hr.HrResumeReuseMapper reuseMapper;

  @org.springframework.beans.factory.annotation.Autowired
  public HrCandidateService(
      HrCandidateRepositoryPort repository,
      ObjectMapper json,
      HrSensitiveJsonCodec codec,
      HrSemanticGateway gateway,
      HrBatchMapper batches,
      HrSourceAuthorization sources,
      com.aiep.platformfile.api.PrivateFileFacade files,
      HrFactChangeService factChanges,
      HrDictionaryService dictionary,
      org.springframework.transaction.PlatformTransactionManager transactions,
      HrIdentityAssociationService associations,
      HrFactNormalization normalization,
      HrResumeReuseService reuse,
      com.aiep.aihub.repository.hr.HrResumeReuseMapper reuseMapper) {
    this(repository, json, codec, gateway, batches);
    this.sources = sources;
    this.files = files;
    this.factChanges = factChanges;
    this.dictionary = dictionary;
    this.transactions =
        new org.springframework.transaction.support.TransactionTemplate(transactions);
    this.associations = associations;
    this.normalization = normalization;
    this.reuse = reuse;
    this.reuseMapper = reuseMapper;
  }

  public HrCandidateService(
      HrCandidateRepositoryPort repository,
      ObjectMapper json,
      HrSensitiveJsonCodec codec,
      HrSemanticGateway gateway) {
    this(repository, json, codec, gateway, null);
  }

  public HrCandidateService(
      HrCandidateRepositoryPort repository,
      ObjectMapper json,
      HrSensitiveJsonCodec codec,
      HrSemanticGateway gateway,
      HrBatchMapper batches) {
    this.repository = repository;
    this.json = json;
    this.codec = codec;
    this.gateway = gateway;
    this.batches = batches;
  }

  public Candidate candidate(HrActor actor, String id) {
    HrAccessPolicy.require(actor, "hr:candidate:read");
    Candidate value = repository.find(actor.tenantId(), id);
    if (value == null) throw HrPositionService.missing();
    if (!"ACTIVE".equals(value.status())
        || value.expiresAt() == null
        || !value.expiresAt().isAfter(Instant.now())) throw HrPositionService.missing();
    HrAccessPolicy.department(actor, value.departmentId());
    HrAccessPolicy.candidate(actor, id);
    HrAccessPolicy.requireFor(actor, "hr:candidate:read", value.departmentId(), id, "CANDIDATE");
    return value;
  }

  public Facts facts(HrActor actor, String id) {
    Candidate c = candidate(actor, id);
    return decode(repository.snapshot(actor.tenantId(), c.currentSnapshotId()));
  }

  public Snapshot snapshot(HrActor actor, String id) {
    Candidate c = candidate(actor, id);
    return repository.snapshot(actor.tenantId(), c.currentSnapshotId());
  }

  public List<Facts> history(HrActor actor, String id) {
    candidate(actor, id);
    return repository.history(actor.tenantId(), id).stream().map(this::decode).toList();
  }

  @Transactional
  public Facts skip(HrActor actor, String id, Skip input) {
    HrAccessPolicy.requireFor(
        actor, "hr:candidate:correct", candidate(actor, id).departmentId(), id, "CANDIDATE");
    if (!input.confirmed()
        || input.reason() == null
        || input.reason().isBlank()
        || input.reason().codePointCount(0, input.reason().length()) > 300) throw invalid();
    Facts old = facts(actor, id);
    var fields =
        old.fields().stream()
            .map(
                f ->
                    "CONFIRMED".equals(f.status())
                        ? f
                        : new Field(
                            f.id(),
                            f.label(),
                            f.value(),
                            "SKIPPED",
                            "人工跳过，仍待核验：" + input.reason(),
                            f.evidenceIds()))
            .toList();
    return save(
        actor,
        id,
        old,
        fields,
        old.structuredFacts(),
        old.blocks(),
        Set.of(),
        input.expectedVersion());
  }

  @Transactional
  public Facts correct(HrActor actor, String id, Corrections request) {
    HrAccessPolicy.require(actor, "hr:candidate:correct");
    Facts old = facts(actor, id);
    HrAccessPolicy.requireFor(
        actor, "hr:candidate:correct", candidate(actor, id).departmentId(), id, "CANDIDATE");
    if (request.changes() == null || request.changes().isEmpty()) throw invalid();
    Map<String, Correction> edits = new HashMap<>();
    for (Correction edit : request.changes()) {
      if (edit == null
          || edit.value() == null
          || edit.value().isBlank()
          || edit.value().length() > 3000
          || edit.reason() == null
          || edit.reason().isBlank()
          || edit.reason().length() > 300
          || edits.put(edit.fieldId(), edit) != null) throw invalid();
    }
    Set<String> ids = new HashSet<>();
    for (Field field : old.fields()) ids.add(field.id());
    if (!ids.containsAll(edits.keySet())) throw invalid();
    if (old.structuredFacts().stream()
        .anyMatch(
            f ->
                edits.containsKey(f.factId())
                    && Set.of("education", "employment", "project", "language", "certificate")
                        .contains(f.kind())))
      throw new HrBusinessException(
          "HR_FACT_STRUCTURED_CORRECTION_REQUIRED", "此事实包含结构化字段，请使用结构化修正", 422);
    List<Field> fields =
        old.fields().stream()
            .map(
                f -> {
                  Correction e = edits.get(f.id());
                  return e == null
                      ? f
                      : new Field(
                          f.id(), f.label(), e.value(), "CONFIRMED", e.reason(), f.evidenceIds());
                })
            .toList();
    return save(
        actor,
        id,
        old,
        fields,
        old.structuredFacts(),
        old.blocks(),
        Set.of(),
        request.expectedVersion());
  }

  @Transactional
  public Facts correctStructured(HrActor actor, String id, StructuredCorrections request) {
    HrAccessPolicy.require(actor, "hr:candidate:correct");
    Facts old = facts(actor, id);
    HrAccessPolicy.requireFor(
        actor, "hr:candidate:correct", candidate(actor, id).departmentId(), id, "CANDIDATE");
    if (request.changes() == null || request.changes().isEmpty()) throw invalid();
    Map<String, StructuredCorrection> changes = new HashMap<>();
    List<Block> sourceBlocks = new ArrayList<>(old.blocks());
    for (StructuredCorrection change : request.changes()) {
      if (change == null
          || change.fact() == null
          || change.reason() == null
          || change.reason().isBlank()
          || change.reason().codePointCount(0, change.reason().length()) > 300
          || changes.put(change.fieldId(), change) != null) throw invalid();
      StructuredFact previous =
          old.structuredFacts().stream()
              .filter(f -> f.factId().equals(change.fieldId()))
              .findFirst()
              .orElseThrow(HrCandidateService::invalid);
      if (!previous.kind().equals(change.fact().kind())
          || !previous.factId().equals(change.fact().factId())) throw invalid();
      StructuredFact corrected = change.fact();
      if (change.humanSource() != null) {
        String source = change.humanSource().strip();
        if (source.isBlank() || source.codePointCount(0, source.length()) > 1000) throw invalid();
        String blockId = "human-" + UUID.randomUUID();
        sourceBlocks.add(new Block(blockId, null, source, "HUMAN_CORRECTION"));
        corrected =
            new StructuredFact(
                corrected.factId(),
                corrected.kind(),
                corrected.value(),
                List.of(
                    new Evidence(blockId, 0, source.codePointCount(0, source.length()), source)),
                corrected.organization(),
                corrected.title(),
                corrected.degree(),
                corrected.major(),
                corrected.startDate(),
                corrected.endDate(),
                corrected.ongoing(),
                corrected.isInternship(),
                corrected.measurement(),
                corrected.backgroundClaim());
      }
      validateStructuredFact(corrected, sourceBlocks);
      changes.put(
          change.fieldId(),
          new StructuredCorrection(
              change.fieldId(), corrected, change.reason(), change.humanSource()));
    }
    List<StructuredFact> structured =
        old.structuredFacts().stream()
            .map(f -> changes.containsKey(f.factId()) ? changes.get(f.factId()).fact() : f)
            .toList();
    List<Field> fields =
        old.fields().stream()
            .map(
                field -> {
                  StructuredCorrection change = changes.get(field.id());
                  return change == null
                      ? field
                      : new Field(
                          field.id(),
                          field.label(),
                          change.fact().value(),
                          "CONFIRMED",
                          change.reason(),
                          change.fact().evidence().stream()
                              .map(Evidence::blockId)
                              .distinct()
                              .toList());
                })
            .toList();
    return save(
        actor,
        id,
        old,
        fields,
        structured,
        sourceBlocks,
        changes.keySet(),
        request.expectedVersion());
  }

  @Transactional
  public Facts confirm(HrActor actor, String id, Confirmations request) {
    HrAccessPolicy.require(actor, "hr:candidate:correct");
    Facts old = facts(actor, id);
    if (request.notApplicableGroups() != null) {
      Set<String> selected = new HashSet<>(request.notApplicableGroups());
      if (!Set.of("employment", "project", "skill", "education", "other").containsAll(selected))
        throw invalid();
      for (var fact : old.structuredFacts())
        if (selected.contains(fact.kind())
            || selected.contains("other")
                && Set.of("certificate", "language").contains(fact.kind())) throw invalid();
      old =
          new Facts(
              old.candidateId(),
              old.resumeVersionId(),
              old.filename(),
              old.pageCount(),
              old.qualityScore(),
              old.status(),
              old.profile(),
              old.blocks(),
              old.fields(),
              old.skills(),
              old.confirmedCount(),
              old.totalCount(),
              old.version(),
              old.structuredFacts(),
              List.copyOf(selected),
              old.normalizations(),
              old.dictionaryVersion());
    }
    HrAccessPolicy.requireFor(
        actor, "hr:candidate:correct", candidate(actor, id).departmentId(), id, "CANDIDATE");
    if (request.fieldIds() == null
        || request.fieldIds().isEmpty()
        || (request.reason() != null && request.reason().length() > 300)) throw invalid();
    Set<String> ids = new HashSet<>();
    for (Field f : old.fields()) ids.add(f.id());
    if (!ids.containsAll(request.fieldIds())) throw invalid();
    if (old.fields().stream()
        .anyMatch(f -> request.fieldIds().contains(f.id()) && f.value().isBlank())) throw invalid();
    List<Field> fields =
        old.fields().stream()
            .map(
                f ->
                    request.fieldIds().contains(f.id())
                        ? new Field(
                            f.id(),
                            f.label(),
                            f.value(),
                            "CONFIRMED",
                            request.reason() == null || request.reason().isBlank()
                                ? "人工核对原文后确认"
                                : request.reason(),
                            f.evidenceIds())
                        : f)
            .toList();
    return save(
        actor,
        id,
        old,
        fields,
        old.structuredFacts(),
        old.blocks(),
        Set.of(),
        request.expectedVersion());
  }

  private Facts save(
      HrActor actor,
      String id,
      Facts old,
      List<Field> fields,
      List<StructuredFact> structured,
      List<Block> sourceBlocks,
      Set<String> structuredChanges,
      long expected) {
    if (old.version() != expected) throw HrPositionService.conflict();
    List<Block> blocks = new ArrayList<>(sourceBlocks);
    List<Field> revisedFields = new ArrayList<>();
    for (Field field : fields) {
      Field previous =
          old.fields().stream().filter(f -> f.id().equals(field.id())).findFirst().orElseThrow();
      if (!field.id().equals("identity-name")
          && !structuredChanges.contains(field.id())
          && !previous.value().equals(field.value())) {
        String blockId = "human-" + UUID.randomUUID();
        blocks.add(
            new Block(
                blockId,
                null,
                "人工修正来源：" + field.label() + "；值：" + field.value() + "；理由：" + field.reason(),
                "HUMAN_CORRECTION"));
        revisedFields.add(
            new Field(
                field.id(),
                field.label(),
                field.value(),
                field.status(),
                field.reason(),
                List.of(blockId)));
      } else revisedFields.add(field);
    }
    fields = List.copyOf(revisedFields);
    List<StructuredFact> revisedStructured = new ArrayList<>();
    for (StructuredFact fact : structured) {
      Field field =
          fields.stream().filter(f -> f.id().equals(fact.factId())).findFirst().orElseThrow();
      if (!field.value().equals(fact.value())) {
        Block source =
            blocks.stream()
                .filter(b -> field.evidenceIds().contains(b.id()))
                .findFirst()
                .orElseThrow();
        revisedStructured.add(
            new StructuredFact(
                fact.factId(),
                fact.kind(),
                field.value(),
                List.of(
                    new Evidence(
                        source.id(),
                        0,
                        source.text().codePointCount(0, source.text().length()),
                        source.text())),
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null));
      } else revisedStructured.add(fact);
    }
    int confirmed = (int) fields.stream().filter(f -> f.status().equals("CONFIRMED")).count();
    String correctedName =
        fields.stream()
            .filter(f -> f.id().equals("identity-name"))
            .map(Field::value)
            .filter(v -> !v.isBlank())
            .findFirst()
            .orElse(old.profile().name());
    Profile profile =
        new Profile(
            correctedName,
            education(revisedStructured, fields),
            experienceMonths(revisedStructured, fields),
            old.profile().targetPosition());
    var normalized =
        normalization == null
            ? null
            : normalization.normalizeFrozen(
                actor,
                candidate(actor, id).departmentId(),
                revisedStructured,
                blocks,
                old.dictionaryVersion());
    Facts next =
        new Facts(
            id,
            old.resumeVersionId(),
            old.filename(),
            old.pageCount(),
            HrQualityPolicy.fields(fields, revisedStructured, Set.copyOf(old.notApplicableGroups()))
                .score(),
            confirmed == fields.size() ? "CONFIRMED" : "NEEDS_REVIEW",
            profile,
            List.copyOf(blocks),
            fields,
            skills(revisedStructured),
            confirmed,
            fields.size(),
            expected + 1,
            List.copyOf(revisedStructured),
            old.notApplicableGroups(),
            normalized == null ? old.normalizations() : normalized.normalizations(),
            normalized == null ? old.dictionaryVersion() : normalized.dictionaryVersion());
    String snapshotId = UUID.randomUUID().toString();
    repository.insertSnapshot(
        new Snapshot(
            snapshotId,
            actor.tenantId(),
            id,
            old.resumeVersionId(),
            next.version(),
            encode(next),
            actor.userId(),
            Instant.now().toString()));
    if (!repository.advance(actor.tenantId(), id, snapshotId, expected))
      throw HrPositionService.conflict();
    repository.staleResults(actor.tenantId(), id);
    if (sources != null)
      sources.confirmationState(
          actor.tenantId(),
          id,
          "CONFIRMED".equals(next.status())
              ? "CONFIRMED"
              : fields.stream().anyMatch(f -> "SKIPPED".equals(f.status()))
                  ? "SKIPPED"
                  : "WAITING");
    if (factChanges != null) factChanges.changed(actor, id, candidate(actor, id).departmentId());
    return next;
  }

  public Facts importResume(HrActor actor, ImportResume request) {
    return importResume(actor, request, UUID.randomUUID().toString(), () -> true);
  }

  public Facts importResume(
      HrActor actor, ImportResume request, String runId, BooleanSupplier live) {
    HrAccessPolicy.require(actor, "hr:candidate:upload");
    HrAccessPolicy.department(actor, request.departmentId());
    HrAccessPolicy.requireFor(
        actor, "hr:candidate:upload", request.departmentId(), null, "CANDIDATE");
    if (!request.consentConfirmed()
        || request.consentVersion() == null
        || request.consentVersion().isBlank())
      throw new HrBusinessException("HR_FACT_CONSENT_REQUIRED", "请先确认简历使用授权", 422);
    com.aiep.aihub.api.hr.HrBatchContracts.Policy policy = validateConsent(actor, request, runId);
    if (request.filename() == null
        || request.filename().isBlank()
        || request.filename().length() > 255
        || request.contentBase64() == null
        || request.contentBase64().length() > 28000000) throw invalid();
    byte[] content;
    try {
      content = Base64.getDecoder().decode(request.contentBase64());
    } catch (IllegalArgumentException error) {
      throw invalid();
    }
    if (content.length == 0 || content.length > 20 * 1024 * 1024) throw invalid();
    String id = UUID.randomUUID().toString(), resumeId = UUID.randomUUID().toString();
    String hash;
    try {
      hash =
          HexFormat.of()
              .formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(content));
    } catch (java.security.NoSuchAlgorithmException e) {
      throw new IllegalStateException(e);
    }
    codec.seal("{}");
    var reused =
        reuse == null ? null : reuse.find(actor, request.departmentId(), hash, request.filename());
    var extractionInput = json.createObjectNode();
    extractionInput.put("candidate_ref", id);
    extractionInput
        .putObject("extraction")
        .put("filename", request.filename())
        .put("content_base64", request.contentBase64())
        .put("sha256", hash);
    checkImportLive(actor, runId, live);
    JsonNode extracted =
        reused == null ? gateway.execute(actor, 6101, runId, extractionInput) : reused.extraction();
    checkImportLive(actor, runId, live);
    if (!hash.equals(extracted.path("content_hash").asText()))
      throw new HrBusinessException("HR_FILE_HASH_MISMATCH", "抽取原件hash不一致", 422);
    JsonNode clean = extracted.path("cleaned_blocks");
    if (!clean.isArray() || clean.isEmpty())
      throw new HrBusinessException("HR_FILE_UNREADABLE", "未提取到有效文本", 422);
    List<Block> blocks = new ArrayList<>();
    int pageCount = 0;
    Set<String> blockIds = new HashSet<>();
    for (JsonNode block : clean) {
      String blockId = block.path("block_id").asText();
      if (blockId.isBlank() || !blockIds.add(blockId) || !block.path("text").isTextual())
        throw invalid();
      Integer page = block.path("page").isInt() ? block.get("page").asInt() : null;
      if (page != null) pageCount = Math.max(pageCount, page);
      List<Double> bbox =
          block.path("bbox").isArray()
              ? json.convertValue(
                  block.path("bbox"),
                  json.getTypeFactory().constructCollectionType(List.class, Double.class))
              : null;
      blocks.add(
          new Block(
              blockId,
              page,
              block.get("text").asText(),
              null,
              bbox,
              block.path("paragraph").isInt() ? block.path("paragraph").asInt() : null,
              block.path("ocr_quality").isNumber() ? block.path("ocr_quality").asDouble() : null));
    }
    var input = json.createObjectNode();
    input.put("candidate_ref", id);
    input.set("blocks", clean);
    checkImportLive(actor, runId, live);
    JsonNode data =
        reused == null
            ? gateway.execute(actor, 6102, runId, input)
            : json.createObjectNode()
                .set("facts", json.valueToTree(reused.originalFacts().structuredFacts()));
    checkImportLive(actor, runId, live);
    if (!data.path("facts").isArray() || data.get("facts").size() > 500) throw invalid();
    List<Field> fields = new ArrayList<>();
    List<Skill> skills = new ArrayList<>();
    Set<String> factIds = new HashSet<>();
    for (JsonNode fact : data.get("facts")) {
      String factId = fact.path("fact_id").asText(),
          kind = fact.path("kind").asText(),
          value = fact.path("value").asText();
      if (!Set.of(
                  "education",
                  "employment",
                  "project",
                  "skill",
                  "language",
                  "certificate",
                  "achievement")
              .contains(kind)
          || factId.isBlank()
          || factId.equals("identity-name")
          || !factIds.add(factId)
          || value.isBlank()
          || value.length() > 3000
          || !fact.path("evidence").isArray()
          || fact.get("evidence").isEmpty()
          || fact.get("evidence").size() > 5) throw invalid();
      List<String> evidence = new ArrayList<>();
      for (JsonNode e : fact.get("evidence")) {
        Block b =
            blocks.stream()
                .filter(x -> x.id().equals(e.path("block_id").asText()))
                .findFirst()
                .orElseThrow(HrCandidateService::invalid);
        validateEvidence(
            b.text(), e.path("start").asInt(-1), e.path("end").asInt(-1), e.path("quote").asText());
        evidence.add(b.id());
      }
      boolean precise = true;
      String reason = "精确原文引用，未检测到归一冲突";
      if (Set.of("employment", "education").contains(kind)
          && (!fact.path("start_date").isObject()
              || "YEAR".equals(fact.path("start_date").path("precision").asText()))) {
        precise = false;
        reason = "日期范围或精度待确认";
      }
      if (Set.of("skill", "certificate", "language").contains(kind)) {
        if (dictionary == null) {
          precise = false;
          reason = "标准词典待确认";
        } else {
          var normalized =
              dictionary.normalizeForUpload(
                  actor,
                  new com.aiep.aihub.api.hr.HrDictionaryContracts.Normalize(
                      request.departmentId(),
                      kind.toUpperCase(Locale.ROOT),
                      value,
                      blocks.stream()
                          .filter(b -> evidence.contains(b.id()))
                          .map(Block::text)
                          .collect(java.util.stream.Collectors.joining("\n"))));
          if (!"NORMALIZED".equals(normalized.status())) {
            precise = false;
            reason = "词典未归一或存在歧义";
          }
        }
      }
      if (blocks.stream()
          .anyMatch(
              b -> evidence.contains(b.id()) && b.ocrQuality() != null && b.ocrQuality() < 0.85)) {
        precise = false;
        reason = "OCR低可靠，需人工核对";
      }
      fields.add(
          new Field(
              factId,
              kind,
              value,
              precise ? "CONFIRMED" : "NEEDS_REVIEW",
              reason,
              List.copyOf(evidence)));
      if (kind.equals("skill"))
        skills.add(
            new Skill(value, "UNKNOWN", new HashSet<>(evidence).size(), List.copyOf(evidence)));
    }
    String name =
        extracted.path("identity").path("name").path("value").isTextual()
            ? extracted.path("identity").path("name").path("value").asText()
            : null;
    fields.add(
        new Field(
            "identity-name",
            "姓名",
            name == null ? "" : name,
            extracted.path("identity").path("name").path("quality").asInt() == 100
                ? "CONFIRMED"
                : "NEEDS_REVIEW",
            "本地身份抽取结果，缺失或冲突须人工核对",
            List.of()));
    List<StructuredFact> structured = new ArrayList<>();
    for (JsonNode fact : data.get("facts")) {
      try {
        StructuredFact value = json.treeToValue(fact, StructuredFact.class);
        validateStructuredFact(value, blocks);
        structured.add(value);
      } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
        throw invalid();
      }
    }
    var quality = HrQualityPolicy.fields(fields, structured);
    var normalized =
        normalization == null
            ? null
            : normalization.normalize(actor, request.departmentId(), structured, blocks);
    int confirmed = (int) fields.stream().filter(f -> "CONFIRMED".equals(f.status())).count();
    Facts facts =
        new Facts(
            id,
            resumeId,
            request.filename(),
            pageCount,
            HrQualityPolicy.fields(fields, structured).score(),
            quality.requiresConfirmation() ? "NEEDS_REVIEW" : "CONFIRMED",
            new Profile(
                name, education(structured, fields), experienceMonths(structured, fields), null),
            List.copyOf(blocks),
            List.copyOf(fields),
            skills(structured),
            confirmed,
            fields.size(),
            1,
            List.copyOf(structured),
            List.of(),
            normalized == null ? List.of() : normalized.normalizations(),
            normalized == null ? null : normalized.dictionaryVersion());
    String snapshotId = UUID.randomUUID().toString();
    Instant acquiredAt = Instant.now();
    Instant expiresAt =
        acquiredAt
            .atZone(java.time.ZoneId.of("Asia/Shanghai"))
            .plusMonths(policy.retentionMonths())
            .toInstant();
    checkImportLive(actor, runId, live);
    Candidate candidate =
        new Candidate(
            id,
            actor.tenantId(),
            request.departmentId(),
            snapshotId,
            1,
            policy.id(),
            acquiredAt,
            expiresAt,
            "ACTIVE");
    if (transactions != null)
      return transactions.execute(
          status ->
              persistImported(
                  actor,
                  request,
                  runId,
                  candidate,
                  snapshotId,
                  resumeId,
                  facts,
                  policy,
                  extracted,
                  content));
    return persistImported(
        actor, request, runId, candidate, snapshotId, resumeId, facts, policy, extracted, content);
  }

  private Facts persistImported(
      HrActor actor,
      ImportResume request,
      String runId,
      Candidate candidate,
      String snapshotId,
      String resumeId,
      Facts facts,
      com.aiep.aihub.api.hr.HrBatchContracts.Policy policy,
      JsonNode extracted,
      byte[] content) {
    String id = candidate.id();
    repository.create(
        candidate,
        new Snapshot(
            snapshotId,
            actor.tenantId(),
            id,
            resumeId,
            1,
            encode(facts),
            actor.userId(),
            Instant.now().toString()));
    if (sources != null) {
      var batch = batches.candidateBatch(actor.tenantId(), id);
      if (batch == null && runId.startsWith("hr-import-")) {
        var item = batches.item(actor.tenantId(), runId.substring("hr-import-".length()));
        if (item != null) batch = batches.batch(actor.tenantId(), item.batchId());
      }
      Set<String> purposes =
          batch != null && "STORE_ONLY".equals(batch.mode())
              ? Set.of("TALENT_POOL", "INTERVIEW")
              : Set.of("RECRUITMENT", "INTERVIEW");
      String fileId =
          files == null
              ? null
              : files.store(actor.tenantId(), id, request.filename(), content).id();
      sources.register(actor, candidate, extracted, purposes, policy.reviewWaitDays(), fileId);
      if (reuseMapper != null
          && reuseMapper.recordHash(actor.tenantId(), id, extracted.path("content_hash").asText())
              != 1) throw new IllegalStateException("HR_SOURCE_HASH_CONFLICT");
      if ("CONFIRMED".equals(facts.status()))
        sources.confirmationState(actor.tenantId(), id, "CONFIRMED");
    }
    if (associations != null) associations.associate(actor, candidate);
    return facts;
  }

  private com.aiep.aihub.api.hr.HrBatchContracts.Policy validateConsent(
      HrActor actor, ImportResume request, String runId) {
    if (batches == null)
      throw new HrBusinessException("HR_FACT_CONSENT_UNAVAILABLE", "无法验证采集授权策略", 503);
    if (runId.startsWith("hr-import-")) {
      var item = batches.item(actor.tenantId(), runId.substring("hr-import-".length()));
      var batch = item == null ? null : batches.batch(actor.tenantId(), item.batchId());
      if (batch == null
          || !batch.userId().equals(actor.userId())
          || !batch.departmentId().equals(request.departmentId())
          || !batch.policyId().equals(request.consentVersion())
          || !batch.status().equals("RUNNING")
          || !item.status().equals("RUNNING"))
        throw new HrBusinessException("HR_FACT_CONSENT_INVALID", "批次授权或运行状态已失效", 409);
      var frozenPolicy = batches.policy(actor.tenantId(), batch.policyId());
      return consentPolicy(frozenPolicy);
    }
    var policy = batches.latestPolicy(actor.tenantId());
    if (policy == null || policy.version() <= 0 || !policy.id().equals(request.consentVersion()))
      throw new HrBusinessException("HR_FACT_CONSENT_INVALID", "采集授权策略已变化，请重新确认", 409);
    return consentPolicy(policy);
  }

  private com.aiep.aihub.api.hr.HrBatchContracts.Policy consentPolicy(HrBatchMapper.PolicyRow row) {
    if (row == null || row.version() <= 0)
      throw new HrBusinessException("HR_FACT_CONSENT_INVALID", "采集授权策略无效", 409);
    try {
      var policy =
          json.readValue(row.payload(), com.aiep.aihub.api.hr.HrBatchContracts.Policy.class);
      if (!row.id().equals(policy.id())
          || policy.version() != row.version()
          || policy.retentionMonths() <= 0
          || policy.retentionMonths() > 36) throw new IllegalArgumentException();
      return policy;
    } catch (com.fasterxml.jackson.core.JsonProcessingException | IllegalArgumentException error) {
      throw new HrBusinessException("HR_FACT_CONSENT_INVALID", "采集授权策略无法验证", 409);
    }
  }

  private void checkImportLive(HrActor actor, String runId, BooleanSupplier live) {
    if (Thread.currentThread().isInterrupted() || !live.getAsBoolean()) {
      gateway.cancel(actor, runId);
      throw new HrBusinessException("HR_RUN_CANCELLED", "材料处理已停止", 409);
    }
  }

  public boolean cancelImport(HrActor actor, String runId) {
    HrAccessPolicy.require(actor, "hr:candidate:upload");
    if (batches == null || !runId.startsWith("hr-import-")) throw invalid();
    var item = batches.item(actor.tenantId(), runId.substring("hr-import-".length()));
    var batch = item == null ? null : batches.batch(actor.tenantId(), item.batchId());
    if (batch == null || !batch.userId().equals(actor.userId())) throw HrPositionService.missing();
    HrAccessPolicy.department(actor, batch.departmentId());
    if (!Set.of("CANCELLED", "FAILED").contains(item.status())
        && !batch.status().equals("CANCELLED"))
      throw new HrBusinessException("HR_RUN_STATE_CONFLICT", "请先持久化停止状态", 409);
    return gateway.cancel(actor, runId);
  }

  private static String education(List<StructuredFact> structured, List<Field> fields) {
    StructuredFact fact = HrFactMeasurements.education(structured, fields);
    return fact == null ? null : fact.degree();
  }

  private static Integer experienceMonths(List<StructuredFact> structured, List<Field> fields) {
    var bounds =
        HrFactMeasurements.experience(
            structured, fields, java.time.LocalDate.now(java.time.ZoneId.of("Asia/Shanghai")));
    return bounds == null || bounds.needsReview() || bounds.minMonths() != bounds.maxMonths()
        ? null
        : Math.toIntExact(bounds.minMonths());
  }

  private static List<Skill> skills(List<StructuredFact> structured) {
    return structured.stream()
        .filter(f -> f.kind().equals("skill"))
        .map(
            f -> {
              Set<String> sources = new HashSet<>();
              Set<String> blocks = new LinkedHashSet<>();
              f.evidence().stream().map(Evidence::blockId).forEach(blocks::add);
              for (var source : structured)
                if (Set.of("employment", "project").contains(source.kind()))
                  for (var evidence : source.evidence())
                    if (evidence.quote().contains(f.value())) {
                      sources.add(HrPositionService.hash(evidence.quote()));
                      blocks.add(evidence.blockId());
                    }
              return new Skill(
                  f.value(),
                  sources.size() >= 2 ? "STRONG" : sources.size() == 1 ? "MEDIUM" : "WEAK",
                  sources.size(),
                  List.copyOf(blocks));
            })
        .toList();
  }

  private static void validateStructuredFact(StructuredFact fact, List<Block> blocks) {
    if (fact.factId() == null
        || fact.factId().isBlank()
        || fact.value() == null
        || fact.value().isBlank()
        || fact.value().codePointCount(0, fact.value().length()) > 3000
        || fact.evidence() == null
        || fact.evidence().isEmpty()
        || fact.evidence().size() > 5) throw invalid();
    StringBuilder quotes = new StringBuilder();
    for (Evidence evidence : fact.evidence()) {
      if (evidence == null || evidence.blockId() == null || evidence.quote() == null)
        throw invalid();
      Block block =
          blocks.stream()
              .filter(b -> b.id().equals(evidence.blockId()))
              .findFirst()
              .orElseThrow(HrCandidateService::invalid);
      validateEvidence(block.text(), evidence.start(), evidence.end(), evidence.quote());
      if (evidence.quote().codePointCount(0, evidence.quote().length()) > 1000) throw invalid();
      quotes.append(evidence.quote()).append('\n');
    }
    for (String value :
        new String[] {fact.organization(), fact.title(), fact.degree(), fact.major()})
      if (value != null && (value.isBlank() || !quotes.toString().contains(value))) throw invalid();
    for (DateValue date : new DateValue[] {fact.startDate(), fact.endDate()}) {
      if (date == null) continue;
      if (date.sourceText() == null
          || date.sourceText().isBlank()
          || !quotes.toString().contains(date.sourceText())) throw invalid();
      try {
        HrFactMeasurements.range(date);
      } catch (RuntimeException error) {
        throw invalid();
      }
    }
    if (Boolean.TRUE.equals(fact.ongoing())
        && (fact.endDate() != null
            || !java.util.regex.Pattern.compile("至今|现在|[Pp]resent").matcher(quotes).find()))
      throw invalid();
    if (Boolean.TRUE.equals(fact.isInternship())
        && !java.util.regex.Pattern.compile("实习|(?i)intern").matcher(quotes).find())
      throw invalid();
    if (fact.measurement() != null) {
      Measurement m = fact.measurement();
      if (!"project".equals(fact.kind())
          || !fact.factId().equals(m.projectId())
          || m.value() != null && m.value().signum() < 0
          || m.roleLevel() != null && (m.roleLevel() < 1 || m.roleLevel() > 3)
          || m.managedTeamSize() != null && m.managedTeamSize() < 0) throw invalid();
      if (m.value() != null
          && (m.metric() == null
              || m.unit() == null
              || !quotes.toString().contains(m.metric())
              || !quotes.toString().contains(m.unit())
              || !quotes.toString().contains(m.value().stripTrailingZeros().toPlainString())))
        throw invalid();
      if (m.roleLevel() != null
          && !java.util.regex.Pattern.compile(
                  switch (m.roleLevel()) {
                    case 1 -> "参与";
                    case 2 -> "核心";
                    default -> "主导|负责";
                  })
              .matcher(quotes)
              .find()) throw invalid();
      if (m.managedTeamSize() != null
          && !java.util.regex.Pattern.compile("管理[^。\\n]{0,20}" + m.managedTeamSize() + "\\s*[人位]")
              .matcher(quotes)
              .find()) throw invalid();
    }
    if (fact.backgroundClaim() != null) {
      String pattern =
          switch (fact.backgroundClaim()) {
            case "ENTREPRENEURSHIP" -> "(?:曾|已|独立)?(?:创业|创办|创立)";
            case "CAREER_TRANSITION" -> "(?:已|从).*(?:转行|转型|跨行业)";
            default -> throw invalid();
          };
      if (!java.util.regex.Pattern.compile(pattern).matcher(quotes).find()
          || java.util.regex.Pattern.compile("计划|希望|准备|打算").matcher(quotes).find()) throw invalid();
    }
  }

  public Facts decode(Snapshot snapshot) {
    if (snapshot == null) throw HrPositionService.missing();
    try {
      return json.readValue(codec.open(snapshot.factsJson()), Facts.class);
    } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
      throw new IllegalStateException("HR_FACT_SNAPSHOT_INVALID");
    }
  }

  public String encode(Facts facts) {
    try {
      return codec.seal(json.writeValueAsString(facts));
    } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
      throw new IllegalStateException("HR_FACT_SNAPSHOT_INVALID");
    }
  }

  public static void validateEvidence(String text, int start, int end, String quote) {
    if (start < 0
        || end <= start
        || end > text.codePointCount(0, text.length())
        || !text.substring(text.offsetByCodePoints(0, start), text.offsetByCodePoints(0, end))
            .equals(quote))
      throw new HrBusinessException("HR_FACT_EVIDENCE_INVALID", "事实引用无效", 422);
  }

  private static HrBusinessException invalid() {
    return new HrBusinessException("HR_FACT_CORRECTION_INVALID", "修正项、来源或理由无效", 422);
  }
}

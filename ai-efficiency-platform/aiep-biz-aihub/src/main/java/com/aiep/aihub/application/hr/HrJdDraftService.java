package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrJdDraftContracts.*;
import com.aiep.aihub.api.hr.HrPositionContracts.*;
import com.aiep.aihub.domain.hr.HrFrozenConfig.*;
import com.aiep.aihub.repository.hr.HrSettingsRepository;
import com.fasterxml.jackson.databind.*;
import java.math.BigDecimal;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 模型生成在事务外；采用双CAS保护JD与岗位草稿，不能直接发布。 */
@Service
public class HrJdDraftService {
  private final HrPositionService positions;
  private final HrSemanticGateway gateway;
  private final HrSettingsRepository repository;
  private final ObjectMapper json;

  public HrJdDraftService(
      HrPositionService positions,
      HrSemanticGateway gateway,
      HrSettingsRepository repository,
      ObjectMapper json) {
    this.positions = positions;
    this.gateway = gateway;
    this.repository = repository;
    this.json = json;
  }

  public JdDraft generate(HrActor actor, String positionId, Generate request) {
    HrAccessPolicy.require(actor, "hr:position:edit");
    var p = positions.get(actor, positionId);
    if (p.version() != request.expectedPositionVersion()) throw HrPositionService.conflict();
    String source = request.text();
    if (source != null && source.length() > 20971520)
      throw HrPositionService.invalid("JD输入超过20MiB");
    if (source == null || source.strip().length() < 100)
      throw HrPositionService.invalid("JD至少100字，不足时不调用模型");
    boolean truncated = source.length() > 20000;
    source = source.substring(0, Math.min(source.length(), 20000));
    var input = json.createObjectNode();
    input.put("jd_text", source);
    String id = UUID.randomUUID().toString();
    JsonNode output = gateway.execute(actor, 6106, "jd-" + id, input);
    JdDraft result = validate(id, p.id(), p.departmentId(), source, truncated, output);
    store(actor, result);
    return result;
  }

  public JdDraft generateFile(
      HrActor actor,
      String positionId,
      long expected,
      org.springframework.web.multipart.MultipartFile file) {
    HrAccessPolicy.require(actor, "hr:position:edit");
    var p = positions.get(actor, positionId);
    if (p.version() != expected) throw HrPositionService.conflict();
    String filename = file.getOriginalFilename() == null ? "" : file.getOriginalFilename();
    String extension =
        filename.substring(filename.lastIndexOf('.') + 1).toLowerCase(java.util.Locale.ROOT);
    if (!Set.of("doc", "docx", "pdf", "txt").contains(extension)
        || file.getSize() < 1
        || file.getSize() > 20971520)
      throw HrPositionService.invalid("JD文件须为doc/docx/pdf/txt且不超过20MiB");
    try {
      byte[] content = file.getBytes();
      var input = json.createObjectNode();
      var extraction = input.putObject("extraction");
      extraction.put("filename", filename);
      extraction.put("content_base64", Base64.getEncoder().encodeToString(content));
      extraction.put(
          "sha256",
          java.util.HexFormat.of()
              .formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(content)));
      var result = gateway.execute(actor, 6101, "jd-extract-" + UUID.randomUUID(), input);
      if (!result.path("blocks").isArray()) throw invalidOutput();
      StringBuilder text = new StringBuilder();
      for (JsonNode block : result.path("blocks")) {
        if (!block.path("text").isTextual()) throw invalidOutput();
        text.append(block.path("text").asText()).append('\n');
      }
      return generate(actor, positionId, new Generate(text.toString(), expected));
    } catch (java.io.IOException | java.security.NoSuchAlgorithmException e) {
      throw new HrBusinessException("HR_JD_FILE_INVALID", "JD文件无法读取", 422);
    }
  }

  @Transactional
  public void store(HrActor actor, JdDraft result) {
    repository.save(
        actor, "JD_DRAFT", result.id(), result.departmentId(), 0, 1, result, "GENERATE");
  }

  public JdDraft get(HrActor actor, String positionId, String id) {
    positions.get(actor, positionId);
    var d = repository.get(actor, "JD_DRAFT", id, JdDraft.class);
    if (!positionId.equals(d.positionId())) throw HrPositionService.missing();
    return d;
  }

  @Transactional
  public JdDraft adopt(HrActor actor, String positionId, String id, Adopt request) {
    HrAccessPolicy.require(actor, "hr:position:edit");
    var d = get(actor, positionId, id);
    var old = positions.draft(actor, positionId);
    if (d.version() != request.expectedVersion()
        || old.version() != request.expectedPositionVersion()) throw HrPositionService.conflict();
    if (request.candidateIds() == null
        || request.candidateIds().isEmpty()
        || new HashSet<>(request.candidateIds()).size() != request.candidateIds().size())
      throw HrPositionService.invalid("请选择未采用候选");
    Map<String, Candidate> byId = new HashMap<>();
    d.candidates().forEach(c -> byId.put(c.id(), c));
    if (!byId.keySet().containsAll(request.candidateIds())
        || request.candidateIds().stream().anyMatch(d.adoptedIds()::contains))
      throw HrPositionService.invalid("候选无效或已采用");
    List<HardRule> hard = new ArrayList<>(old.hardConditions());
    List<SemanticCriterion> criteria = new ArrayList<>(old.criteria());
    var prior = old.draftScoring();
    if (prior == null && old.scoring() != null) {
      var s = old.scoring();
      prior =
          new DraftScoring(
              s.version(),
              s.weights(),
              s.requirements(),
              s.highThreshold(),
              s.middleThreshold(),
              s.lowThreshold(),
              s.minimumCoverage(),
              s.strongCoverage());
    }
    if (prior == null) throw HrPositionService.invalid("请先选择岗位族评分模板");
    List<Requirement> requirements = new ArrayList<>(prior.requirements());
    for (String selected : request.candidateIds()) {
      var c = byId.get(selected);
      if (c.hardRule() != null) hard.add(c.hardRule());
      if (c.criterion() != null) {
        criteria.add(c.criterion());
        if (c.hardRule() == null)
          requirements.add(
              new Requirement(
                  c.id(),
                  Dimension.valueOf(c.criterion().dimension()),
                  c.skill() == null ? BigDecimal.ONE : BigDecimal.valueOf(c.skill().importance()),
                  false,
                  true));
      }
    }
    var scoring =
        new DraftScoring(
            "draft",
            prior.weights(),
            requirements,
            prior.highThreshold(),
            prior.middleThreshold(),
            prior.lowThreshold(),
            prior.minimumCoverage(),
            prior.strongCoverage());
    positions.save(
        actor,
        positionId,
        new Draft(
            old.positionId(),
            old.name(),
            old.family(),
            old.departmentId(),
            old.level(),
            old.jdText(),
            "SOFT_REQUIREMENTS",
            null,
            hard,
            criteria,
            old.version(),
            scoring));
    List<String> adopted = new ArrayList<>(d.adoptedIds());
    adopted.addAll(request.candidateIds());
    var next =
        new JdDraft(
            d.id(),
            d.positionId(),
            d.departmentId(),
            d.sourceText(),
            d.truncated(),
            d.candidates(),
            d.safetyWarnings(),
            d.version() + 1,
            adopted);
    repository.save(
        actor, "JD_DRAFT", id, d.departmentId(), d.version(), next.version(), next, "ADOPT");
    return next;
  }

  public static JdDraft validate(
      String id,
      String position,
      String department,
      String text,
      boolean truncated,
      JsonNode output) {
    if (!output.path("candidates").isArray() || output.path("candidates").size() > 60)
      throw invalidOutput();
    List<Candidate> candidates = new ArrayList<>();
    List<String> warnings = new ArrayList<>();
    Set<String> unique = new HashSet<>();
    for (JsonNode item : output.get("candidates")) {
      String description = item.path("criterion").asText("");
      String quote = item.path("source_quote").asText("");
      String type = item.path("type").asText();
      String dimension = item.path("dimension").asText();
      if (description.isBlank()
          || description.length() > 1000
          || quote.isBlank()
          || quote.length() > 1000
          || !text.contains(quote)
          || item.path("default_adopted").asBoolean(false)
          || !Set.of("HARD_CONDITION", "SKILL", "EXPERIENCE", "PROJECT").contains(type)
          || !Set.of("SKILL", "EXPERIENCE", "PROJECT", "EDUCATION", "BONUS").contains(dimension)
          || !"HARD_CONDITION".equals(type) && !type.equals(dimension)) throw invalidOutput();
      boolean prohibited;
      try {
        HrProtectedAttributes.validateRule(description, quote);
        prohibited = false;
      } catch (HrBusinessException excluded) {
        prohibited = true;
      }
      if (prohibited) {
        if (warnings.isEmpty()) warnings.add("已移除含禁用属性的候选，不进入评分规则");
        continue;
      }
      if (!unique.add(type + description + "\n" + quote)) continue;
      String key =
          switch (type) {
            case "HARD_CONDITION" -> "hard_condition";
            case "SKILL" -> "skill";
            case "EXPERIENCE" -> "experience";
            default -> "project";
          };
      for (String candidateKey : List.of("hard_condition", "skill", "experience", "project"))
        if (candidateKey.equals(key)
            ? !item.path(candidateKey).isObject()
            : item.hasNonNull(candidateKey)) throw invalidOutput();
      String candidateId = "jd-" + UUID.randomUUID();
      HardRule hard = null;
      SkillProposal skill = null;
      ExperienceProposal experience = null;
      ProjectProposal project = null;
      Calculation calculation = null;
      JsonNode proposal = item.path(key);
      if ("HARD_CONDITION".equals(type)) {
        String hardType = proposal.path("type").asText();
        try {
          com.aiep.aihub.domain.hr.HrHardConditionEvaluator.Type.valueOf(hardType);
        } catch (RuntimeException e) {
          throw invalidOutput();
        }
        List<String> values = new ArrayList<>();
        for (JsonNode value : proposal.path("values")) {
          if (!value.isTextual() || value.asText().isBlank() || value.asText().length() > 200)
            throw invalidOutput();
          values.add(value.asText());
        }
        if (values.size() > 20) throw invalidOutput();
        String mode = proposal.path("match_mode").asText("ALL");
        if (!Set.of("ALL", "ANY").contains(mode)) throw invalidOutput();
        BigDecimal threshold = decimal(proposal, "threshold");
        boolean semantic =
            Set.of("REQUIRED_SKILL", "CERTIFICATE", "LOCATION", "LANGUAGE").contains(hardType);
        if (semantic && values.isEmpty()
            || !semantic && (threshold == null || threshold.signum() <= 0)) throw invalidOutput();
        hard =
            new HardRule(
                candidateId,
                hardType,
                description,
                description,
                proposal.path("unit").asText(null),
                threshold,
                BigDecimal.ZERO,
                false,
                values,
                mode);
      }
      if ("SKILL".equals(type)) {
        String name = proposal.path("name").asText();
        Integer level = integer(proposal, "expected_level", 1, 5);
        Integer importance = integer(proposal, "importance", 1, 10);
        if (name.isBlank() || name.length() > 200) throw invalidOutput();
        skill = new SkillProposal(name, level, importance == null ? 5 : importance);
      }
      if ("EXPERIENCE".equals(type)) {
        Integer min = integer(proposal, "minimum_months", 1, 1200),
            max = integer(proposal, "maximum_months", 1, 1200);
        if (min != null && max != null && min > max) throw invalidOutput();
        experience =
            new ExperienceProposal(
                min, max, bounded(proposal, "industry", 200), bounded(proposal, "function", 200));
        if (min != null && max != null)
          calculation =
              new Calculation(
                  "EXPERIENCE_MONTHS",
                  BigDecimal.valueOf(min),
                  BigDecimal.valueOf(max),
                  null,
                  null,
                  null);
      }
      if ("PROJECT".equals(type)) {
        String metric = bounded(proposal, "metric", 100), unit = bounded(proposal, "unit", 100);
        BigDecimal scale = decimal(proposal, "expected_scale");
        Integer role = integer(proposal, "expected_role", 1, 3),
            team = integer(proposal, "managed_team_size", 1, 100000);
        if (scale != null && scale.signum() <= 0) throw invalidOutput();
        project = new ProjectProposal(metric, unit, scale, role, team);
        if (scale != null && metric != null && unit != null)
          calculation = new Calculation("PROJECT_SCALE", null, null, scale, metric, unit);
        else if (role != null)
          calculation =
              new Calculation("PROJECT_ROLE", null, null, BigDecimal.valueOf(role), null, null);
        else if (team != null)
          calculation =
              new Calculation("TEAM_SIZE", null, null, BigDecimal.valueOf(team), null, null);
      }
      var semantic =
          new SemanticCriterion(
              candidateId, description, dimension, description, "", "", "", "", false, calculation);
      int start = text.indexOf(quote);
      candidates.add(
          new Candidate(
              candidateId,
              type,
              description,
              quote,
              start,
              start + quote.length(),
              hard,
              semantic,
              skill,
              experience,
              project));
    }
    return new JdDraft(
        id, position, department, text, truncated, candidates, warnings, 1, List.of());
  }

  private static String bounded(JsonNode node, String key, int max) {
    if (!node.hasNonNull(key)) return null;
    if (!node.path(key).isTextual() || node.path(key).asText().length() > max)
      throw invalidOutput();
    return node.path(key).asText();
  }

  private static Integer integer(JsonNode node, String key, int min, int max) {
    if (!node.hasNonNull(key)) return null;
    if (!node.path(key).isIntegralNumber() || !node.path(key).canConvertToInt())
      throw invalidOutput();
    int value = node.path(key).asInt();
    if (value < min || value > max) throw invalidOutput();
    return value;
  }

  private static BigDecimal decimal(JsonNode node, String key) {
    if (!node.hasNonNull(key)) return null;
    try {
      if (!node.path(key).isNumber() && !node.path(key).isTextual()) throw invalidOutput();
      BigDecimal value = new BigDecimal(node.path(key).asText());
      if (value.abs().compareTo(new BigDecimal("1000000000000")) > 0) throw invalidOutput();
      return value;
    } catch (NumberFormatException e) {
      throw invalidOutput();
    }
  }

  private static HrBusinessException invalidOutput() {
    return new HrBusinessException("HR_JD_CONTRACT_INVALID", "JD候选缺少有效原句或违反默认不采用约束", 502);
  }
}

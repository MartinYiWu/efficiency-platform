package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrDictionaryContracts.*;
import com.aiep.aihub.api.hr.HrDictionaryContracts.Dictionary;
import com.aiep.aihub.repository.hr.HrSettingsRepository;
import java.text.Normalizer;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 词典导入先列冲突，采用时CAS整批写入；从不修改已有事实。 */
@Service
public class HrDictionaryService {
  private static final Set<String> CATEGORIES =
      Set.of("SKILL", "INDUSTRY", "FUNCTION", "DEGREE", "MAJOR", "CERTIFICATE", "LANGUAGE");
  private final HrSettingsRepository repository;

  public HrDictionaryService(HrSettingsRepository repository) {
    this.repository = repository;
  }

  public Dictionary get(HrActor actor, String department) {
    HrAccessPolicy.requireFor(actor, "hr:config:read", department, null, "CONFIG");
    return repository.exists(actor, "DICTIONARY", department)
        ? repository.get(actor, "DICTIONARY", department, Dictionary.class)
        : new Dictionary(department, "DEFAULT", List.of(), 0);
  }

  @Transactional
  public Dictionary save(HrActor actor, Save input) {
    HrAccessPolicy.require(actor, "hr:config:edit");
    var old = get(actor, input.departmentId());
    if (old.version() != input.expectedVersion()) throw HrPositionService.conflict();
    var errors = conflicts(input.entries());
    if (!errors.isEmpty()) throw HrPositionService.invalid("词典存在冲突，请先预检修正");
    var next = new Dictionary(old.departmentId(), "DRAFT", input.entries(), old.version() + 1);
    repository.save(
        actor,
        "DICTIONARY",
        old.departmentId(),
        old.departmentId(),
        old.version(),
        next.version(),
        next,
        "SAVE_DRAFT");
    return next;
  }

  @Transactional
  public Dictionary publish(HrActor actor, String department, long expected) {
    HrAccessPolicy.require(actor, "hr:config:publish");
    var old = get(actor, department);
    if (old.version() != expected || old.version() == 0) throw HrPositionService.conflict();
    var next = new Dictionary(department, "PUBLISHED", old.entries(), old.version() + 1);
    repository.save(
        actor,
        "DICTIONARY",
        department,
        department,
        old.version(),
        next.version(),
        next,
        "PUBLISH");
    return next;
  }

  public List<Dictionary> versions(HrActor actor, String department) {
    get(actor, department);
    return repository.versions(actor, "DICTIONARY", department, Dictionary.class);
  }

  @Transactional
  public ImportPreview preflight(HrActor actor, Save input) {
    HrAccessPolicy.require(actor, "hr:config:edit");
    var old = get(actor, input.departmentId());
    if (old.version() != input.expectedVersion()) throw HrPositionService.conflict();
    var rows = input.entries() == null ? List.<Entry>of() : input.entries();
    if (repository.encode(rows).getBytes(java.nio.charset.StandardCharsets.UTF_8).length > 10485760)
      throw HrPositionService.invalid("导入超过10MiB");
    var preview =
        new ImportPreview(
            UUID.randomUUID().toString(),
            input.departmentId(),
            old.version(),
            rows,
            conflicts(rows),
            1);
    repository.save(
        actor,
        "DICTIONARY_IMPORT",
        preview.id(),
        preview.departmentId(),
        0,
        1,
        preview,
        "PREFLIGHT");
    return preview;
  }

  @Transactional
  public Dictionary adopt(HrActor actor, String id, long expected) {
    HrAccessPolicy.require(actor, "hr:config:edit");
    var p = repository.get(actor, "DICTIONARY_IMPORT", id, ImportPreview.class);
    if (p.version() != expected || p.version() != 1) throw HrPositionService.conflict();
    if (!p.conflicts().isEmpty()) throw HrPositionService.invalid("导入存在冲突，整批未采用");
    var result = save(actor, new Save(p.departmentId(), p.baseVersion(), p.entries()));
    repository.save(
        actor,
        "DICTIONARY_IMPORT",
        id,
        p.departmentId(),
        p.version(),
        2,
        new ImportPreview(id, p.departmentId(), p.baseVersion(), p.entries(), List.of(), 2),
        "ADOPT");
    return result;
  }

  public Normalized normalize(HrActor actor, Normalize input) {
    HrAccessPolicy.requireFor(actor, "hr:config:read", input.departmentId(), null, "CONFIG");
    return normalizePublished(actor, input, "hr:config:read", "CONFIG");
  }

  public Normalized normalizeForUpload(HrActor actor, Normalize input) {
    HrAccessPolicy.requireFor(
        actor, "hr:candidate:upload", input.departmentId(), null, "CANDIDATE");
    return normalizePublished(actor, input, "hr:candidate:upload", "CANDIDATE");
  }

  private Normalized normalizePublished(
      HrActor actor, Normalize input, String permission, String kind) {
    if (!CATEGORIES.contains(input.category())) throw HrPositionService.invalid("词典类别无效");
    Dictionary published =
        repository.exists(actor, "DICTIONARY", input.departmentId())
            ? repository
                .publicationHistory(
                    actor, "DICTIONARY", input.departmentId(), Dictionary.class, permission, kind)
                .stream()
                .filter(d -> "PUBLISHED".equals(d.status()))
                .findFirst()
                .orElse(new Dictionary(input.departmentId(), "DEFAULT", List.of(), 0))
            : new Dictionary(input.departmentId(), "DEFAULT", List.of(), 0);
    return normalizeAt(published, input);
  }

  public Dictionary publishedForUpload(HrActor actor, String department) {
    HrAccessPolicy.requireFor(actor, "hr:candidate:upload", department, null, "CANDIDATE");
    return repository.exists(actor, "DICTIONARY", department)
        ? repository
            .publicationHistory(
                actor,
                "DICTIONARY",
                department,
                Dictionary.class,
                "hr:candidate:upload",
                "CANDIDATE")
            .stream()
            .filter(d -> "PUBLISHED".equals(d.status()))
            .findFirst()
            .orElse(new Dictionary(department, "DEFAULT", List.of(), 0))
        : new Dictionary(department, "DEFAULT", List.of(), 0);
  }

  public Dictionary publishedForCorrection(HrActor actor, String department, long version) {
    HrAccessPolicy.requireFor(actor, "hr:candidate:correct", department, null, "CANDIDATE");
    if (version == 0) return new Dictionary(department, "DEFAULT", List.of(), 0);
    if (version < 0 || !repository.exists(actor, "DICTIONARY", department))
      throw new HrBusinessException(
          "HR_DICTIONARY_VERSION_NOT_FOUND", "原事实冻结词典版本不可访问，请保留未归一状态", 409);
    return repository
        .publicationHistory(
            actor, "DICTIONARY", department, Dictionary.class, "hr:candidate:correct", "CANDIDATE")
        .stream()
        .filter(d -> d.version() == version && "PUBLISHED".equals(d.status()))
        .findFirst()
        .orElseThrow(
            () ->
                new HrBusinessException(
                    "HR_DICTIONARY_VERSION_NOT_FOUND", "原事实冻结词典版本不存在，不自动切换新词典", 409));
  }

  public static Normalized normalizeAt(Dictionary published, Normalize input) {
    if (!CATEGORIES.contains(input.category())) throw HrPositionService.invalid("词典类别无效");
    if (input.text() == null || input.text().isBlank() || input.text().length() > 200)
      return new Normalized(
          input.text(), null, "UNNORMALIZED", published.version(), List.of(), null);
    String text = key(HrPositionService.text(input.text(), 200));
    String context = input.context() == null ? "" : input.context();
    var matches =
        published.entries().stream()
            .filter(
                e ->
                    e.category().equals(input.category())
                        && (key(e.canonical()).equals(text)
                            || e.aliases().stream().anyMatch(a -> key(a).equals(text))))
            .filter(
                e ->
                    e.contextPattern() == null
                        || e.contextPattern().isBlank()
                        || context.contains(e.contextPattern()))
            .map(Entry::canonical)
            .distinct()
            .toList();
    return new Normalized(
        input.text(),
        matches.size() == 1 ? matches.getFirst() : null,
        matches.size() == 1 ? "NORMALIZED" : "UNNORMALIZED",
        published.version(),
        matches,
        matches.size() == 1
            ? published.entries().stream()
                .filter(
                    e ->
                        e.category().equals(input.category())
                            && e.canonical().equals(matches.getFirst()))
                .map(Entry::id)
                .findFirst()
                .orElse(null)
            : null);
  }

  public String export(HrActor actor, String department) {
    var d = get(actor, department);
    StringBuilder csv = new StringBuilder("id,category,canonical,aliases,contextPattern\r\n");
    for (var e : d.entries())
      csv.append(cell(e.id()))
          .append(',')
          .append(cell(e.category()))
          .append(',')
          .append(cell(e.canonical()))
          .append(',')
          .append(cell(String.join("|", e.aliases())))
          .append(',')
          .append(cell(e.contextPattern()))
          .append("\r\n");
    return csv.toString();
  }

  private static String cell(String value) {
    String s = value == null ? "" : value;
    if (!s.isEmpty() && "=+-@".indexOf(s.charAt(0)) >= 0) s = "'" + s;
    return "\"" + s.replace("\"", "\"\"") + "\"";
  }

  public static List<Conflict> conflicts(List<Entry> rows) {
    List<Conflict> errors = new ArrayList<>();
    if (rows == null || rows.size() > 10000) {
      return List.of(new Conflict(0, "ROW_LIMIT", "导入最多10000行"));
    }
    Map<String, Entry> canonical = new HashMap<>();
    Map<String, List<Entry>> names = new HashMap<>();
    Set<String> ids = new HashSet<>();
    for (int i = 0; i < rows.size(); i++) {
      var e = rows.get(i);
      if (e == null
          || e.id() == null
          || e.id().isBlank()
          || !ids.add(e.id())
          || !CATEGORIES.contains(e.category())
          || e.canonical() == null
          || e.canonical().isBlank()
          || e.canonical().length() > 200
          || e.aliases().size() > 100
          || e.aliases().stream().anyMatch(a -> a == null || a.isBlank() || a.length() > 200)
          || e.contextPattern() != null && e.contextPattern().length() > 200) {
        errors.add(new Conflict(i + 1, "INVALID_ENTRY", "词条格式、类别或ID无效"));
        continue;
      }
      String scope = e.category() + ":";
      if (canonical.putIfAbsent(scope + key(e.canonical()), e) != null)
        errors.add(new Conflict(i + 1, "DUPLICATE_CANONICAL", "同类别标准名重复"));
      var aliases = new HashSet<String>();
      aliases.add(key(e.canonical()));
      for (String alias : e.aliases())
        if (!aliases.add(key(alias))) errors.add(new Conflict(i + 1, "DUPLICATE_ALIAS", "词条内别名重复"));
      for (String name : aliases)
        names.computeIfAbsent(scope + name, k -> new ArrayList<>()).add(e);
    }
    for (var pair : names.entrySet()) {
      var entries = pair.getValue();
      if (entries.size() > 1) {
        Set<String> contexts = new HashSet<>();
        if (entries.stream()
            .anyMatch(
                e ->
                    e.contextPattern() == null
                        || e.contextPattern().isBlank()
                        || !contexts.add(e.contextPattern())))
          errors.add(new Conflict(0, "AMBIGUOUS_ALIAS", "跨词条别名需要不同上下文消歧规则"));
      }
    }
    return List.copyOf(errors);
  }

  private static String key(String value) {
    return Normalizer.normalize(value, Normalizer.Form.NFKC).strip().toLowerCase(Locale.ROOT);
  }
}

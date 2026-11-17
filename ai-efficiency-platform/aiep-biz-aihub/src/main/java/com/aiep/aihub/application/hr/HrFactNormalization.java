package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.api.hr.HrDictionaryContracts.Normalize;
import java.util.*;
import org.springframework.stereotype.Service;

/** 一次归一冻结一个已发布词典；原文事实不覆盖，标准ID/质量另行保存。 */
@Service
public class HrFactNormalization {
  public record Result(Long dictionaryVersion, List<FactNormalization> normalizations) {
    public Result {
      normalizations = List.copyOf(normalizations);
    }
  }

  private final HrDictionaryService dictionary;

  public HrFactNormalization(HrDictionaryService dictionary) {
    this.dictionary = dictionary;
  }

  public Result normalize(
      HrActor actor, String department, List<StructuredFact> facts, List<Block> blocks) {
    var published = dictionary.publishedForUpload(actor, department);
    return normalizeWith(published, facts, blocks);
  }

  public Result normalizeFrozen(
      HrActor actor,
      String department,
      List<StructuredFact> facts,
      List<Block> blocks,
      Long dictionaryVersion) {
    HrAccessPolicy.requireFor(actor, "hr:candidate:correct", department, null, "CANDIDATE");
    if (dictionaryVersion == null) return new Result(null, List.of());
    return normalizeWith(
        dictionary.publishedForCorrection(actor, department, dictionaryVersion), facts, blocks);
  }

  private Result normalizeWith(
      com.aiep.aihub.api.hr.HrDictionaryContracts.Dictionary published,
      List<StructuredFact> facts,
      List<Block> blocks) {
    List<FactNormalization> rows = new ArrayList<>();
    for (var fact : facts) {
      String context =
          fact.evidence() == null
              ? ""
              : fact.evidence().stream()
                  .map(Evidence::quote)
                  .collect(java.util.stream.Collectors.joining("\n"));
      String category =
          switch (fact.kind()) {
            case "skill" -> "SKILL";
            case "certificate" -> "CERTIFICATE";
            case "language" -> "LANGUAGE";
            default -> null;
          };
      if (category != null)
        add(rows, published, fact.factId(), category, fact.value(), context, fact, blocks);
      if ("education".equals(fact.kind())) {
        if (fact.degree() != null && !fact.degree().isBlank())
          add(rows, published, fact.factId(), "DEGREE", fact.degree(), context, fact, blocks);
        if (fact.major() != null && !fact.major().isBlank())
          add(rows, published, fact.factId(), "MAJOR", fact.major(), context, fact, blocks);
      }
    }
    return new Result(published.version(), rows);
  }

  private static void add(
      List<FactNormalization> rows,
      com.aiep.aihub.api.hr.HrDictionaryContracts.Dictionary dictionary,
      String factId,
      String category,
      String original,
      String context,
      StructuredFact fact,
      List<Block> blocks) {
    var normalized =
        HrDictionaryService.normalizeAt(
            dictionary, new Normalize(dictionary.departmentId(), category, original, context));
    boolean exact =
        fact.evidence() != null
            && !fact.evidence().isEmpty()
            && fact.evidence().stream()
                .allMatch(
                    e ->
                        blocks.stream()
                            .anyMatch(b -> b.id().equals(e.blockId()) && valid(b.text(), e)));
    boolean lowOcr =
        fact.evidence() != null
            && fact.evidence().stream()
                .anyMatch(
                    e ->
                        blocks.stream()
                            .anyMatch(
                                b ->
                                    b.id().equals(e.blockId())
                                        && b.ocrQuality() != null
                                        && b.ocrQuality() < 0.85));
    int quality = !exact || lowOcr ? 40 : "NORMALIZED".equals(normalized.status()) ? 100 : 60;
    rows.add(
        new FactNormalization(
            factId,
            category,
            original,
            normalized.standardId(),
            normalized.canonical(),
            normalized.status(),
            dictionary.version(),
            quality));
  }

  private static boolean valid(String text, Evidence e) {
    if (text == null
        || e.start() < 0
        || e.end() <= e.start()
        || e.end() > text.codePointCount(0, text.length())) return false;
    return text.substring(
            text.offsetByCodePoints(0, e.start()), text.offsetByCodePoints(0, e.end()))
        .equals(e.quote());
  }
}

package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import java.math.*;
import java.util.*;

/** quality-policy/1仅描述解析材料的可核对程度，不代表事实真实性或候选能力。 */
public final class HrQualityPolicy {
  public static boolean hasEvidenceConflict(Facts facts) {
    return facts.fields().stream()
        .anyMatch(
            f ->
                "CONFLICT".equals(f.status())
                    || !"CONFIRMED".equals(f.status())
                        && f.reason() != null
                        && (f.reason().contains("冲突") || f.reason().contains("矛盾")));
  }

  private static final Map<String, Integer> WEIGHTS =
      Map.of("name", 10, "employment", 30, "project", 25, "skill", 20, "education", 10, "other", 5);

  private HrQualityPolicy() {}

  public record Quality(int score, boolean requiresConfirmation) {}

  public static Quality evaluate(
      Map<String, Integer> values, Set<String> notApplicable, int weakHardFacts) {
    int sum = 0, weight = 0;
    for (var item : WEIGHTS.entrySet()) {
      if (notApplicable.contains(item.getKey())) continue;
      int v = values.getOrDefault(item.getKey(), 0);
      if (v < 0 || v > 100) throw new IllegalArgumentException("invalid quality");
      sum += v * item.getValue();
      weight += item.getValue();
    }
    int score =
        weight == 0
            ? 0
            : BigDecimal.valueOf(sum)
                .divide(BigDecimal.valueOf(weight), 0, RoundingMode.HALF_UP)
                .intValueExact();
    return new Quality(
        score, values.getOrDefault("name", 0) == 0 || score < 70 || weakHardFacts >= 2);
  }

  public static Quality fields(List<Field> fields, List<StructuredFact> facts) {
    return fields(fields, facts, Set.of());
  }

  public static Quality fields(
      List<Field> fields, List<StructuredFact> facts, Set<String> notApplicable) {
    Map<String, List<Integer>> groups = new HashMap<>();
    for (Field f : fields) {
      String group =
          f.id().equals("identity-name")
              ? "name"
              : Set.of("employment", "project", "skill", "education").contains(f.label())
                  ? f.label()
                  : "other";
      int quality =
          f.value() == null || f.value().isBlank()
              ? 0
              : "CONFIRMED".equals(f.status())
                  ? 100
                  : f.reason() != null && (f.reason().contains("冲突") || f.reason().contains("OCR"))
                      ? 40
                      : f.evidenceIds() == null || f.evidenceIds().isEmpty() ? 0 : 60;
      groups.computeIfAbsent(group, k -> new ArrayList<>()).add(quality);
    }
    Map<String, Integer> averages = new HashMap<>();
    groups.forEach(
        (g, values) ->
            averages.put(
                g,
                (int) Math.round(values.stream().mapToInt(Integer::intValue).average().orElse(0))));
    return evaluate(averages, notApplicable, 0);
  }

  public static long weakHardFacts(
      List<Field> fields, List<com.aiep.aihub.api.hr.HrPositionContracts.HardRule> rules) {
    Set<String> required = new HashSet<>();
    for (var r : rules)
      switch (r.type()) {
        case "EDUCATION" -> required.add("education");
        case "WORK_EXPERIENCE" -> required.add("employment");
        case "REQUIRED_SKILL" -> required.add("skill");
        case "CERTIFICATE" -> required.add("certificate");
        case "LANGUAGE" -> required.add("language");
        case "PROJECT_SCALE", "TEAM_SIZE" -> required.add("project");
        default -> {}
      }
    return fields.stream()
        .filter(f -> required.contains(f.label()) && !"CONFIRMED".equals(f.status()))
        .count();
  }
}

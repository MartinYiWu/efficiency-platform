package com.aiep.aihub.application.hr;

import java.text.Normalizer;
import java.util.*;

/** resume-dedup/1只比较已脱敏可见文本，不推断身份。 */
public final class HrTalentDedup {
  private static final Map<Integer, String> CASE_FOLD = caseFoldTable();

  private HrTalentDedup() {}

  public record ContactSignal(
      String kind, String value, int quality, boolean shared, boolean conflict) {}

  public enum IdentityDecision {
    AUTO_LINK,
    MANUAL_REVIEW,
    UNRELATED
  }

  public static IdentityDecision identity(
      List<ContactSignal> incoming, List<ContactSignal> existing) {
    if (incoming == null || existing == null) return IdentityDecision.UNRELATED;
    List<ContactSignal>
        a = incoming.stream().filter(s -> s.value() != null && !s.value().isBlank()).toList(),
        b = existing.stream().filter(s -> s.value() != null && !s.value().isBlank()).toList();
    if (a.stream().anyMatch(s -> s.shared() || s.conflict())
        || b.stream().anyMatch(s -> s.shared() || s.conflict()))
      return IdentityDecision.MANUAL_REVIEW;
    boolean matched = false;
    for (String kind : List.of("PHONE", "EMAIL")) {
      Set<String> left = new HashSet<>(), right = new HashSet<>();
      a.stream()
          .filter(s -> kind.equals(s.kind()) && s.quality() == 100)
          .forEach(s -> left.add(contactKey(s)));
      b.stream()
          .filter(s -> kind.equals(s.kind()) && s.quality() == 100)
          .forEach(s -> right.add(contactKey(s)));
      if (left.size() > 1 || right.size() > 1) return IdentityDecision.MANUAL_REVIEW;
      if (!left.isEmpty() && !right.isEmpty()) {
        if (!left.equals(right)) return IdentityDecision.MANUAL_REVIEW;
        matched = true;
      }
    }
    if (!matched) return IdentityDecision.UNRELATED;
    if (a.stream().anyMatch(s -> s.quality() != 100)
        || b.stream().anyMatch(s -> s.quality() != 100)) return IdentityDecision.MANUAL_REVIEW;
    return IdentityDecision.AUTO_LINK;
  }

  private static String contactKey(ContactSignal signal) {
    String normalized =
        Normalizer.normalize(signal.value(), Normalizer.Form.NFKC).strip().toLowerCase(Locale.ROOT);
    return "PHONE".equals(signal.kind()) ? normalized.replaceAll("[\\s()\\-]", "") : normalized;
  }

  public static double similarity(String left, String right) {
    int[] a = normalize(left), b = normalize(right);
    if (a.length == 0 || b.length == 0) return 0;
    int n = Math.min(a.length, b.length) >= 20 ? 5 : Math.min(3, Math.min(a.length, b.length));
    Set<String> x = grams(a, n), y = grams(b, n), intersection = new HashSet<>(x);
    intersection.retainAll(y);
    x.addAll(y);
    return x.isEmpty() ? 0 : (double) intersection.size() / x.size();
  }

  private static int[] normalize(String value) {
    StringBuilder folded = new StringBuilder();
    Normalizer.normalize(value, Normalizer.Form.NFKC)
        .codePoints()
        .forEach(
            cp -> folded.append(CASE_FOLD.getOrDefault(cp, new String(Character.toChars(cp)))));
    return folded
        .toString()
        .codePoints()
        .filter(
            c ->
                !Character.isWhitespace(c)
                    && !Character.isSpaceChar(c)
                    && Character.getType(c) != Character.FORMAT
                    && !Character.isISOControl(c))
        .toArray();
  }

  private static Map<Integer, String> caseFoldTable() {
    try (var input = HrTalentDedup.class.getResourceAsStream("/hr-unicode-casefold.txt")) {
      if (input == null) throw new IllegalStateException("HR_CASEFOLD_TABLE_MISSING");
      var result = new HashMap<Integer, String>();
      for (String line :
          new String(input.readAllBytes(), java.nio.charset.StandardCharsets.UTF_8).split("\\n")) {
        if (line.isBlank() || line.startsWith("#")) continue;
        var fields = line.strip().split("=", 2);
        var folded = new StringBuilder();
        for (String point : fields[1].split(","))
          folded.appendCodePoint(Integer.parseInt(point, 16));
        result.put(Integer.parseInt(fields[0], 16), folded.toString());
      }
      return Map.copyOf(result);
    } catch (java.io.IOException error) {
      throw new IllegalStateException("HR_CASEFOLD_TABLE_INVALID", error);
    }
  }

  private static Set<String> grams(int[] value, int n) {
    Set<String> result = new HashSet<>();
    for (int i = 0; i <= value.length - n; i++) result.add(new String(value, i, n));
    return result;
  }
}

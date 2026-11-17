package com.aiep.aihub.api.hr;

import java.util.List;

/** 七类词典及导入预检；发布版本只影响新归一。 */
public final class HrDictionaryContracts {
  private HrDictionaryContracts() {}

  public record Entry(
      String id, String category, String canonical, List<String> aliases, String contextPattern) {
    public Entry {
      aliases = aliases == null ? List.of() : List.copyOf(aliases);
    }
  }

  public record Dictionary(String departmentId, String status, List<Entry> entries, long version) {
    public Dictionary {
      entries = List.copyOf(entries);
    }
  }

  public record Save(String departmentId, long expectedVersion, List<Entry> entries) {}

  public record Conflict(int row, String code, String message) {}

  public record ImportPreview(
      String id,
      String departmentId,
      long baseVersion,
      List<Entry> entries,
      List<Conflict> conflicts,
      long version) {
    public ImportPreview {
      entries = List.copyOf(entries);
      conflicts = List.copyOf(conflicts);
    }
  }

  public record Normalize(String departmentId, String category, String text, String context) {}

  public record Normalized(
      String original,
      String canonical,
      String status,
      long dictionaryVersion,
      List<String> matches,
      String standardId) {
    public Normalized(
        String original,
        String canonical,
        String status,
        long dictionaryVersion,
        List<String> matches) {
      this(original, canonical, status, dictionaryVersion, matches, null);
    }
  }
}

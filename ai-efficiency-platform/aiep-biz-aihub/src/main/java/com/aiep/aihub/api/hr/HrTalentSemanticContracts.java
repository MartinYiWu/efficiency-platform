package com.aiep.aihub.api.hr;

import java.time.Instant;
import java.util.List;

/** 语义检索相关度不进入匹配评分；显式确认POST才允许受控模型执行。 */
public final class HrTalentSemanticContracts {
  private HrTalentSemanticContracts() {}

  public record SearchRequest(String query, boolean confirmed, List<String> candidateIds) {}

  public record Match(String blockId, int start, int end, String quote) {}

  public record Hit(
      String candidateId,
      double retrievalRelevance,
      List<Match> matches,
      String status,
      String failureCode) {}

  public record SearchJob(
      String id, String status, String query, List<Hit> hits, Instant createdAt) {}
}

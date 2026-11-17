package com.aiep.aihub.api.hr;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

/** 运行和反馈合同不承载模型输入，断线恢复仅返回已保存公开事件。 */
public final class HrExecutionContracts {
  private HrExecutionContracts() {}

  public record FeedbackRequest(String expectedSnapshotHash, String rating, String reason) {}

  public record Feedback(
      String id,
      String resultId,
      String rating,
      String reason,
      String actorId,
      Instant createdAt) {}

  public record RecalculationPreview(String inputHash, List<PreviewItem> items, int modelCalls) {}

  public record PreviewItem(
      String sourceResultId,
      String candidateId,
      BigDecimal oldScore,
      BigDecimal newScore,
      String businessStatus,
      String band,
      BigDecimal coverage) {}
}

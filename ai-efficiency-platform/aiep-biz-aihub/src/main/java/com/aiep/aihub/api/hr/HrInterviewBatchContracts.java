package com.aiep.aihub.api.hr;

import java.util.List;

public final class HrInterviewBatchContracts {
  private HrInterviewBatchContracts() {}

  public record GenerationBatch(
      List<HrInterviewContracts.GenerateRequest> items, boolean confirmed) {}

  public record ExportBatch(List<HrInterviewContracts.ExportRequest> items, boolean confirmed) {}

  public record Item(
      String candidateId,
      String status,
      String setId,
      String exportId,
      String grantId,
      String errorCode) {}

  public record Batch(String id, String status, List<Item> items) {}
}

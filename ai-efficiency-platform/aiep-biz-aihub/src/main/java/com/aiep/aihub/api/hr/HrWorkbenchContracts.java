package com.aiep.aihub.api.hr;

import java.util.List;

/** 工作台仅投影有权的真实业务计数，不从模型或演示数据生成指标。 */
public final class HrWorkbenchContracts {
  private HrWorkbenchContracts() {}

  public record Metric(String key, String label, long value, String comparisonText) {}

  public record Todo(String key, String label, long count, String path) {}

  public record PositionProgress(
      String id, String name, long matched, long filtered, long reviewRequired) {}

  public record Activity(String id, String occurredAt, String label) {}

  public record Workbench(
      List<Metric> metrics,
      List<Todo> todos,
      List<PositionProgress> positions,
      List<Activity> activities) {}
}

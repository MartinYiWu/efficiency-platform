package com.aiep.aihub.domain.hr;

import java.math.*;
import java.util.*;

/** 硬条件保守判断：区间跨过门槛不臆选端点，未提及不视为失败。 */
public final class HrHardConditionEvaluator {
  public enum Type {
    EDUCATION,
    WORK_EXPERIENCE,
    REQUIRED_SKILL,
    LOCATION,
    CERTIFICATE,
    LANGUAGE,
    PROJECT_SCALE,
    TEAM_SIZE
  }

  public enum Status {
    PASS,
    BORDERLINE,
    FAIL,
    UNKNOWN,
    NEEDS_REVIEW,
    OVERRIDDEN
  }

  public enum MatchMode {
    ALL,
    ANY
  }

  public record Result(
      String id, Type type, Status status, boolean overrideAllowed, String reasonCode) {
    public Result {
      Objects.requireNonNull(id);
      Objects.requireNonNull(type);
      Objects.requireNonNull(status);
      Objects.requireNonNull(reasonCode);
    }
  }

  public Result numeric(
      String id,
      Type type,
      BigDecimal required,
      BigDecimal minimum,
      BigDecimal maximum,
      boolean tolerance,
      boolean conflict) {
    return numeric(id, type, required, minimum, maximum, tolerance, conflict, 0);
  }

  public Result numeric(
      String id,
      Type type,
      BigDecimal required,
      BigDecimal minimum,
      BigDecimal maximum,
      boolean tolerance,
      boolean conflict,
      int metricPrecision) {
    if (metricPrecision < 0 || metricPrecision > 12)
      throw new IllegalArgumentException("invalid metric precision");
    if (required.signum() <= 0) throw new IllegalArgumentException("positive requirement needed");
    if (conflict) return result(id, type, Status.NEEDS_REVIEW);
    if (minimum == null || maximum == null) return result(id, type, Status.UNKNOWN);
    if (minimum.signum() < 0 || minimum.compareTo(maximum) > 0)
      throw new IllegalArgumentException("invalid actual interval");
    BigDecimal allowance = BigDecimal.ZERO;
    if (tolerance)
      allowance =
          switch (type) {
            case EDUCATION -> BigDecimal.ONE;
            case WORK_EXPERIENCE, LANGUAGE, TEAM_SIZE ->
                required.multiply(new BigDecimal("0.30")).setScale(0, RoundingMode.FLOOR);
            case PROJECT_SCALE ->
                required
                    .multiply(new BigDecimal("0.30"))
                    .setScale(metricPrecision, RoundingMode.FLOOR);
            default -> BigDecimal.ZERO;
          };
    BigDecimal relaxed = required.subtract(allowance);
    if (minimum.compareTo(required) >= 0) return result(id, type, Status.PASS);
    if (minimum.compareTo(relaxed) >= 0 && maximum.compareTo(required) < 0)
      return result(id, type, Status.BORDERLINE);
    if (maximum.compareTo(relaxed) < 0) return result(id, type, Status.FAIL);
    return result(id, type, Status.UNKNOWN);
  }

  public Result combine(String id, Type type, MatchMode mode, List<Status> statuses) {
    if (statuses.isEmpty() || statuses.contains(Status.OVERRIDDEN))
      throw new IllegalArgumentException("invalid atomic conditions");
    if (mode == MatchMode.ALL && statuses.contains(Status.FAIL))
      return result(id, type, Status.FAIL);
    if (mode == MatchMode.ANY && statuses.contains(Status.PASS))
      return result(id, type, Status.PASS);
    if (mode == MatchMode.ANY && statuses.contains(Status.BORDERLINE))
      return result(id, type, Status.BORDERLINE);
    if (statuses.contains(Status.NEEDS_REVIEW)) return result(id, type, Status.NEEDS_REVIEW);
    if (statuses.contains(Status.UNKNOWN)) return result(id, type, Status.UNKNOWN);
    if (mode == MatchMode.ALL)
      return result(
          id, type, statuses.contains(Status.BORDERLINE) ? Status.BORDERLINE : Status.PASS);
    return result(id, type, Status.FAIL);
  }

  private Result result(String id, Type type, Status status) {
    return new Result(
        id, type, status, type != Type.REQUIRED_SKILL && type != Type.CERTIFICATE, status.name());
  }
}

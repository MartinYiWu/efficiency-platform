package com.aiep.aihub.repository.hr;

import java.sql.*;
import java.time.Instant;
import org.apache.ibatis.type.*;

/** 对外ISO时间不得作为VARCHAR写MySQL时间列；只在明确时间字段上注册。 */
public final class HrTimestampStringHandler extends BaseTypeHandler<String> {
  @Override
  public void setNonNullParameter(
      PreparedStatement statement, int index, String value, JdbcType type) throws SQLException {
    statement.setTimestamp(index, Timestamp.from(Instant.parse(value)));
  }

  @Override
  public String getNullableResult(ResultSet rows, String column) throws SQLException {
    return iso(rows.getTimestamp(column));
  }

  @Override
  public String getNullableResult(ResultSet rows, int column) throws SQLException {
    return iso(rows.getTimestamp(column));
  }

  @Override
  public String getNullableResult(CallableStatement statement, int column) throws SQLException {
    return iso(statement.getTimestamp(column));
  }

  private static String iso(Timestamp timestamp) {
    return timestamp == null ? null : timestamp.toInstant().toString();
  }
}

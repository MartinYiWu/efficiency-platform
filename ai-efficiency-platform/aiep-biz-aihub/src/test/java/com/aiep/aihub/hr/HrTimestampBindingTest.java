package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.repository.hr.HrTimestampStringHandler;
import java.sql.*;
import java.time.Instant;
import org.apache.ibatis.type.JdbcType;
import org.junit.jupiter.api.Test;

class HrTimestampBindingTest {
  @Test
  void iso_snapshot_time_is_bound_as_jdbc_timestamp_not_varchar() throws Exception {
    var statement = mock(PreparedStatement.class);
    String value = "2026-11-11T07:32:35.123456789Z";
    new HrTimestampStringHandler().setNonNullParameter(statement, 1, value, JdbcType.TIMESTAMP);
    verify(statement).setTimestamp(1, Timestamp.from(Instant.parse(value)));
    verify(statement, never()).setString(anyInt(), anyString());
  }

  @Test
  void jdbc_time_is_read_back_as_iso_utc() throws Exception {
    var result = mock(ResultSet.class);
    when(result.getTimestamp("created_at"))
        .thenReturn(Timestamp.from(Instant.parse("2026-11-11T07:32:35Z")));
    assertEquals(
        "2026-11-11T07:32:35Z",
        new HrTimestampStringHandler().getNullableResult(result, "created_at"));
  }
}

package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.HrCandidateContracts.Run;
import com.aiep.aihub.repository.hr.*;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.Environment;
import org.apache.ibatis.session.*;
import org.apache.ibatis.transaction.jdbc.JdbcTransactionFactory;
import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.Test;

class HrBatchScopeCancellationTest {
  @Test
  void persisted_scope_cancellation_records_events_and_rejects_late_success() throws Exception {
    var ds = new JdbcDataSource();
    ds.setURL("jdbc:h2:mem:scope_cancel_" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1");
    try (var c = ds.getConnection();
        var st = c.createStatement()) {
      for (String sql :
          Files.readString(
                  Path.of("../sql/migration/V1.2.0__hr_positions_candidates_and_matching.sql"))
              .split(";")) if (!sql.isBlank()) st.execute(sql);
    }
    var cfg = new Configuration(new Environment("test", new JdbcTransactionFactory(), ds));
    cfg.setMapUnderscoreToCamelCase(true);
    cfg.addMapper(HrMatchingMapper.class);
    try (var xml =
        Files.newInputStream(Path.of("src/main/resources/mapper/hr/HrMatchingMapper.xml"))) {
      new XMLMapperBuilder(xml, cfg, "scope", cfg.getSqlFragments()).parse();
    }
    try (var session = new SqlSessionFactoryBuilder().build(cfg).openSession(true)) {
      var mapper = session.getMapper(HrMatchingMapper.class);
      var events = mock(HrExecutionMapper.class);
      var repository = new HrMatchingRepository(mapper, mock(HrCandidateMapper.class), events);
      Instant now = Instant.now();
      for (String id : List.of("first", "second")) {
        repository.insertRun(
            new Run(
                id,
                "t",
                "c",
                "p",
                "PENDING",
                null,
                null,
                now,
                "cipher",
                now.plusSeconds(600),
                "key-" + id,
                "hash",
                "hr-import-item"));
      }
      assertTrue(repository.start("t", "first"));
      repository.cancelScope("t", "hr-import-item");
      assertEquals("CANCEL_PENDING", mapper.run("t", "first").status());
      assertEquals("CANCEL_PENDING", mapper.run("t", "second").status());
      assertEquals(0, mapper.finishRun("t", "first", "SUCCEEDED", "late", null));
      repository.confirmScopeCancellation("t", "hr-import-item");
      assertEquals("CANCELLED", mapper.run("t", "first").status());
      assertEquals(0, mapper.finishRun("t", "first", "SUCCEEDED", "later", null));
      verify(events)
          .recordEvent(
              argThat(
                  e ->
                      e.runId().equals("first")
                          && e.sequence() == 3
                          && e.status().equals("CANCEL_PENDING")));
      verify(events)
          .recordEvent(
              argThat(
                  e ->
                      e.runId().equals("first")
                          && e.sequence() == 4
                          && e.status().equals("CANCELLED")));
      assertFalse(repository.completeRun("t", "first", null, null));
    }
  }
}

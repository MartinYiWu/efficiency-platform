package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;

import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.repository.hr.*;
import java.io.*;
import java.nio.file.*;
import java.time.Instant;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.Environment;
import org.apache.ibatis.session.*;
import org.apache.ibatis.transaction.jdbc.JdbcTransactionFactory;
import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.*;

class HrMatchingPersistenceTest {
  SqlSession session;
  HrMatchingMapper mapper;

  @BeforeEach
  void setup() throws Exception {
    JdbcDataSource ds = new JdbcDataSource();
    ds.setURL("jdbc:h2:mem:match_" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1");
    String ddl =
        Files.readString(
            Path.of("../sql/migration/V1.2.0__hr_positions_candidates_and_matching.sql"));
    try (var c = ds.getConnection();
        var statement = c.createStatement()) {
      for (String sql : ddl.split(";")) if (!sql.isBlank()) statement.execute(sql);
      statement.execute("ALTER TABLE ai_hr_matching_result ADD total_score DECIMAL(5,1)");
      statement.execute("ALTER TABLE ai_hr_matching_result ADD evidence_coverage DECIMAL(5,1)");
      statement.execute("ALTER TABLE ai_hr_matching_result ADD band VARCHAR(32)");
    }
    Configuration config =
        new Configuration(new Environment("test", new JdbcTransactionFactory(), ds));
    config.setMapUnderscoreToCamelCase(true);
    config.addMapper(HrMatchingMapper.class);
    try (InputStream xml =
        Files.newInputStream(Path.of("src/main/resources/mapper/hr/HrMatchingMapper.xml"))) {
      new XMLMapperBuilder(xml, config, "hr", config.getSqlFragments()).parse();
    }
    session = new SqlSessionFactoryBuilder().build(config).openSession(true);
    mapper = session.getMapper(HrMatchingMapper.class);
  }

  @AfterEach
  void close() {
    if (session != null) session.close();
  }

  Run pending() {
    return new Run(
        "run",
        "t",
        "c",
        "p",
        "PENDING",
        null,
        null,
        Instant.parse("2026-11-11T00:00:00Z"),
        "sealed",
        Instant.parse("2026-11-11T00:10:00Z"),
        "idem-12345",
        "a".repeat(64),
        "scope-run");
  }

  @Test
  void onlyOneWorkerCanStartAndDeadlineIsPreserved() {
    mapper.insertRun(pending());
    assertEquals(1, mapper.startRun("t", "run"));
    assertEquals(0, mapper.startRun("t", "run"));
    assertEquals(pending().deadlineAt(), mapper.run("t", "run").deadlineAt());
    assertNull(mapper.run("other", "run"));
  }

  @Test
  void cancellationCannotBeOverwrittenByLateSuccess() {
    mapper.insertRun(pending());
    mapper.startRun("t", "run");
    assertEquals(1, mapper.cancelRun("t", "run"));
    assertEquals(0, mapper.finishRun("t", "run", "SUCCEEDED", "late", null));
    assertEquals("CANCEL_PENDING", mapper.run("t", "run").status());
    mapper.confirmCancellation("t", "run", false);
    assertEquals("HR_CANCEL_NOT_CONFIRMED", mapper.run("t", "run").failureCode());
    mapper.confirmCancellation("t", "run", true);
    assertEquals("CANCELLED", mapper.run("t", "run").status());
  }

  @Test
  void idempotencyKeyFindsSamePersistedRequestAndDuplicateIsRejected() {
    mapper.insertRun(pending());
    assertEquals("run", mapper.findIdempotency("t", "idem-12345").id());
    assertThrows(
        RuntimeException.class,
        () ->
            mapper.insertRun(
                new Run(
                    "another",
                    "t",
                    "c",
                    "p",
                    "PENDING",
                    null,
                    null,
                    pending().createdAt(),
                    "sealed",
                    pending().deadlineAt(),
                    "idem-12345",
                    "a".repeat(64),
                    "scope-run")));
  }
}

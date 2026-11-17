package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;

import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.repository.hr.*;
import java.io.*;
import java.nio.file.*;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.Environment;
import org.apache.ibatis.session.*;
import org.apache.ibatis.transaction.jdbc.JdbcTransactionFactory;
import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.Test;

class HrCandidatePersistenceTest {
  @Test
  void snapshotIsImmutableAndOnlyOneConcurrentVersionCanAdvance() throws Exception {
    JdbcDataSource ds = new JdbcDataSource();
    ds.setURL("jdbc:h2:mem:hr_" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1");
    String ddl =
        Files.readString(
            Path.of("../sql/migration/V1.2.0__hr_positions_candidates_and_matching.sql")
                .normalize());
    try (var c = ds.getConnection();
        var statement = c.createStatement()) {
      for (String sql : ddl.split(";")) if (!sql.isBlank()) statement.execute(sql);
    }
    Configuration config =
        new Configuration(new Environment("test", new JdbcTransactionFactory(), ds));
    config.setMapUnderscoreToCamelCase(true);
    config.addMapper(HrCandidateMapper.class);
    try (InputStream xml =
        Files.newInputStream(Path.of("src/main/resources/mapper/hr/HrCandidateMapper.xml"))) {
      new XMLMapperBuilder(xml, config, "hr", config.getSqlFragments()).parse();
    }
    try (SqlSession session = new SqlSessionFactoryBuilder().build(config).openSession(true)) {
      HrCandidateMapper mapper = session.getMapper(HrCandidateMapper.class);
      mapper.insertCandidate(new Candidate("c", "t", "d", "s1", 1));
      mapper.insertSnapshot(
          new Snapshot("s1", "t", "c", "r", 1, "sealed-1", "1", "2026-11-11T00:00:00Z"));
      mapper.insertSnapshot(
          new Snapshot("s2", "t", "c", "r", 2, "sealed-2", "1", "2026-11-11T00:00:01Z"));
      assertEquals(1, mapper.advance("t", "c", "s2", 1));
      assertEquals(0, mapper.advance("t", "c", "lost", 1));
      assertEquals("sealed-1", mapper.snapshot("t", "s1").factsJson());
      assertEquals("s2", mapper.find("t", "c").currentSnapshotId());
      assertNull(mapper.find("other", "c"));
    }
  }
}

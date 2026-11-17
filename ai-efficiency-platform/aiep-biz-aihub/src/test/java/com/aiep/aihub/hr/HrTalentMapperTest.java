package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;

import com.aiep.aihub.repository.hr.HrTalentMapper;
import java.io.*;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.Environment;
import org.apache.ibatis.session.*;
import org.apache.ibatis.transaction.jdbc.JdbcTransactionFactory;
import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.Test;

class HrTalentMapperTest {
  @Test
  void persisted_acl_merge_versions_and_one_use_grants_survive_sessions() throws Exception {
    var ds = new JdbcDataSource();
    ds.setURL("jdbc:h2:mem:talent_" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1");
    try (var connection = ds.getConnection();
        var st = connection.createStatement()) {
      for (String file :
          List.of(
              "V1.2.0__hr_positions_candidates_and_matching.sql",
              "V1.2.2__hr_talent_interview_extensions.sql"))
        for (String sql :
            Files.readString(Path.of("../sql/migration/" + file)).replace("\uFEFF", "").split(";"))
          if (!sql.isBlank()) st.execute(sql);
      st.execute(
          "INSERT INTO"
              + " ai_hr_candidate(id,tenant_id,department_id,current_snapshot_id,version,status,expires_at)"
              + " VALUES('a','t','d','s',1,'ACTIVE','2030-01-01'),('b','t','other','s',1,'ACTIVE','2030-01-01'),('e','t','d','s',1,'ACTIVE','2020-01-01')");
    }
    var cfg = new Configuration(new Environment("test", new JdbcTransactionFactory(), ds));
    cfg.setMapUnderscoreToCamelCase(true);
    cfg.addMapper(HrTalentMapper.class);
    try (var xml =
        Files.newInputStream(Path.of("src/main/resources/mapper/hr/HrCandidateMapper.xml"))) {
      new XMLMapperBuilder(xml, cfg, "candidate", cfg.getSqlFragments()).parse();
    }
    try (var xml =
        Files.newInputStream(Path.of("src/main/resources/mapper/hr/HrTalentMapper.xml"))) {
      new XMLMapperBuilder(xml, cfg, "talent", cfg.getSqlFragments()).parse();
    }
    var factory = new SqlSessionFactoryBuilder().build(cfg);
    Instant now = Instant.parse("2026-11-11T00:00:00Z");
    try (var session = factory.openSession(true)) {
      var m = session.getMapper(HrTalentMapper.class);
      assertEquals(1, m.visible("t", Set.of("d"), Set.of("a"), now).size());
      assertTrue(m.visible("t", Set.of("d"), Set.of("b"), now).isEmpty());
      m.insertGrant(new HrTalentMapper.GrantRow("g", "t", "a", "u", now.plusSeconds(30), "ACTIVE"));
      assertEquals(1, m.consumeGrant("t", "g", now));
      assertEquals(0, m.consumeGrant("t", "g", now));
      m.insertMerge(
          new HrTalentMapper.MergeRow(
              "merge",
              "t",
              "a",
              "[\"a\",\"b\"]",
              "ACTIVE",
              now,
              now.plus(Duration.ofDays(7)),
              1,
              "u"));
      m.insertSource("t", "a", "a", "merge");
      m.insertSource("t", "b", "a", "merge");
      assertEquals(2, m.sources("t", "a").size());
      assertEquals(0, m.revokeMerge("t", "merge", 99));
      assertEquals(1, m.revokeMerge("t", "merge", 1));
    }
    try (var session = factory.openSession(true)) {
      assertEquals("CONSUMED", session.getMapper(HrTalentMapper.class).grant("t", "g").status());
      assertEquals("REVOKED", session.getMapper(HrTalentMapper.class).merge("t", "merge").status());
    }
  }
}

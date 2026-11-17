package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;

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

class HrTalentIdentityArchivePersistenceTest {
  @Test
  void hmac_lookup_is_scoped_and_archive_moves_only_after_receipt() throws Exception {
    var ds = new JdbcDataSource();
    ds.setURL("jdbc:h2:mem:talent_privacy_" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1");
    try (var c = ds.getConnection();
        var st = c.createStatement()) {
      for (String migration :
          List.of(
              "V1.2.0__hr_positions_candidates_and_matching.sql",
              "V1.2.2__hr_talent_interview_extensions.sql",
              "V1.2.5__hr_identity_association.sql",
              "V1.2.6__hr_audit_archive.sql"))
        for (String sql :
            Files.readString(Path.of("../sql/migration/" + migration))
                .replace("\uFEFF", "")
                .split(";")) if (!sql.isBlank()) st.execute(sql);
      st.execute(
          "INSERT INTO"
              + " ai_hr_candidate(id,tenant_id,department_id,current_snapshot_id,version,status,expires_at)"
              + " VALUES('a','t','d','s',1,'ACTIVE','2030-01-01'),('b','t','private','s',1,'ACTIVE','2030-01-01')");
      st.execute(
          "INSERT INTO"
              + " ai_hr_audit(id,tenant_id,action,actor_id,subject_ref,department_id,occurred_at)"
              + " VALUES('old','t','VIEW','u','hash','d','2020-01-01'),('new','t','VIEW','u','hash','d','2026-01-01')");
    }
    var cfg = new Configuration(new Environment("test", new JdbcTransactionFactory(), ds));
    cfg.setMapUnderscoreToCamelCase(true);
    for (Class<?> type : List.of(HrTalentIdentityMapper.class, HrAuditArchiveMapper.class)) {
      cfg.addMapper(type);
      try (var xml =
          Files.newInputStream(
              Path.of("src/main/resources/mapper/hr/" + type.getSimpleName() + ".xml"))) {
        new XMLMapperBuilder(xml, cfg, type.getSimpleName(), cfg.getSqlFragments()).parse();
      }
    }
    try (var session = new SqlSessionFactoryBuilder().build(cfg).openSession(true)) {
      var identity = session.getMapper(HrTalentIdentityMapper.class);
      identity.signal(
          new HrTalentIdentityMapper.Signal("t", "a", "EMAIL", "hmac", 100, false, false));
      identity.signal(
          new HrTalentIdentityMapper.Signal("t", "b", "EMAIL", "hmac", 100, false, false));
      assertEquals(
          Set.of("a"),
          identity.possible(
              "t", "incoming", Set.of("hmac"), Set.of("d"), Set.of("*"), Instant.now()));
      assertTrue(
          identity
              .possible(
                  "other", "incoming", Set.of("hmac"), Set.of("d"), Set.of("*"), Instant.now())
              .isEmpty());
      var archive = session.getMapper(HrAuditArchiveMapper.class);
      Instant before = Instant.parse("2023-11-11T00:00:00Z");
      assertEquals(0, archive.removeArchivedHot(before));
      assertEquals(1, archive.archive(before, Instant.now()));
      assertEquals(1, archive.removeArchivedHot(before));
      assertEquals(0, archive.archive(before, Instant.now()));
      assertEquals(0, archive.expireCold(Instant.parse("2016-11-11T00:00:00Z")));
    }
  }
}

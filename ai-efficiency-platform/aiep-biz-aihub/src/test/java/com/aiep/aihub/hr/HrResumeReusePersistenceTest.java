package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;

import com.aiep.aihub.repository.hr.HrResumeReuseMapper;
import java.nio.file.*;
import java.time.Instant;
import java.util.Set;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.Environment;
import org.apache.ibatis.session.*;
import org.apache.ibatis.transaction.jdbc.JdbcTransactionFactory;
import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.Test;

class HrResumeReusePersistenceTest {
  @Test
  void wildcard_scope_reuses_original_version_and_excludes_other_department_and_expired()
      throws Exception {
    var ds = new JdbcDataSource();
    ds.setURL("jdbc:h2:mem:reuse_" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1");
    try (var connection = ds.getConnection();
        var statement = connection.createStatement()) {
      for (var file :
          new String[] {
            "V1.2.0__hr_positions_candidates_and_matching.sql",
            "V1.2.3__hr_execution_identity_and_sources.sql",
            "V1.2.14__hr_resume_reuse_hash.sql"
          })
        for (var sql : Files.readString(Path.of("../sql/migration", file)).split(";"))
          if (!sql.isBlank()) statement.execute(sql);
      statement.execute(
          "INSERT INTO"
              + " ai_hr_candidate(id,tenant_id,department_id,current_snapshot_id,version,status,expires_at)"
              + " VALUES('c','t','d','v2',2,'ACTIVE','2030-01-01'),('other','t','private','x',1,'ACTIVE','2030-01-01'),('expired','t','d','e',1,'ACTIVE','2020-01-01')");
      for (var id : new String[] {"c", "other", "expired"}) {
        statement.execute(
            "INSERT INTO"
                + " ai_hr_source_authorization(tenant_id,candidate_id,policy_id,purposes,identity_json,extraction_json,wait_until,continuation_state,content_hash)"
                + " VALUES('t','"
                + id
                + "','p','RECRUITMENT','cipher','extraction','2030-01-01','WAITING','hash')");
        statement.execute(
            "INSERT INTO"
                + " ai_hr_fact_snapshot(id,tenant_id,candidate_id,resume_version_id,version,facts_json,created_by,created_at)"
                + " VALUES('"
                + id
                + "-v1','t','"
                + id
                + "','r',1,'original-v1','1','2026-11-11')");
      }
      statement.execute(
          "INSERT INTO"
              + " ai_hr_fact_snapshot(id,tenant_id,candidate_id,resume_version_id,version,facts_json,created_by,created_at)"
              + " VALUES('v2','t','c','r',2,'edited-v2','1','2026-11-11')");
    }
    var cfg = new Configuration(new Environment("test", new JdbcTransactionFactory(), ds));
    cfg.setMapUnderscoreToCamelCase(true);
    cfg.addMapper(HrResumeReuseMapper.class);
    try (var xml =
        Files.newInputStream(Path.of("src/main/resources/mapper/hr/HrResumeReuseMapper.xml"))) {
      new XMLMapperBuilder(xml, cfg, "reuse", cfg.getSqlFragments()).parse();
    }
    try (var session = new SqlSessionFactoryBuilder().build(cfg).openSession(true)) {
      var mapper = session.getMapper(HrResumeReuseMapper.class);
      var rows = mapper.find("t", "d", "hash", Set.of("*"), Instant.parse("2026-11-11T00:00:00Z"));
      assertEquals(1, rows.size());
      assertEquals("original-v1", rows.getFirst().factsJson());
      assertTrue(mapper.find("t", "d", "hash", Set.of("other"), Instant.now()).isEmpty());
    }
  }
}

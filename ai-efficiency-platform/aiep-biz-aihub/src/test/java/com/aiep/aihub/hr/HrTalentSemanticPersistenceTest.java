package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;

import com.aiep.aihub.repository.hr.HrTalentSemanticMapper;
import java.nio.file.*;
import java.time.*;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.Environment;
import org.apache.ibatis.session.*;
import org.apache.ibatis.transaction.jdbc.JdbcTransactionFactory;
import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.Test;

class HrTalentSemanticPersistenceTest {
  @Test
  void job_compare_and_set_and_source_deletion_survive_reopening() throws Exception {
    var ds = new JdbcDataSource();
    ds.setURL("jdbc:h2:mem:semantic_" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1");
    try (var c = ds.getConnection();
        var st = c.createStatement()) {
      for (String sql :
          Files.readString(Path.of("../sql/migration/V1.2.11__hr_semantic_search.sql"))
              .replace("\uFEFF", "")
              .split(";")) if (!sql.isBlank()) st.execute(sql);
    }
    var cfg = new Configuration(new Environment("test", new JdbcTransactionFactory(), ds));
    cfg.setMapUnderscoreToCamelCase(true);
    cfg.addMapper(HrTalentSemanticMapper.class);
    try (var xml =
        Files.newInputStream(Path.of("src/main/resources/mapper/hr/HrTalentSemanticMapper.xml"))) {
      new XMLMapperBuilder(xml, cfg, "semantic", cfg.getSqlFragments()).parse();
    }
    var factory = new SqlSessionFactoryBuilder().build(cfg);
    try (var session = factory.openSession(true)) {
      var m = session.getMapper(HrTalentSemanticMapper.class);
      m.insert(
          new HrTalentSemanticMapper.Row(
              "j",
              "t",
              "u",
              "PREFLIGHT",
              "encrypted-input",
              "encrypted-result",
              "key",
              "hash",
              Instant.now(),
              Instant.now()));
      m.source("t", "j", "c");
      assertEquals(
          1,
          m.update(
              "t",
              "j",
              "PREFLIGHT",
              "RUNNING",
              "encrypted-input",
              "encrypted-result",
              Instant.now()));
      assertEquals(
          0,
          m.update(
              "t",
              "j",
              "PREFLIGHT",
              "RUNNING",
              "encrypted-input",
              "encrypted-result",
              Instant.now()));
      assertNull(m.find("other", "j"));
    }
    try (var session = factory.openSession(true)) {
      var m = session.getMapper(HrTalentSemanticMapper.class);
      assertEquals("RUNNING", m.find("t", "j").status());
      m.recover();
      assertEquals("FAILED", m.find("t", "j").status());
      m.deleteJobsForSource("t", "c");
      m.deleteSourceRefs("t", "c");
      assertNull(m.find("t", "j"));
    }
  }
}

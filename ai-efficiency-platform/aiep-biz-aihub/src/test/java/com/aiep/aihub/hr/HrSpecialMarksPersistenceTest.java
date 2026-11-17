package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;

import com.aiep.aihub.repository.hr.HrSpecialMarksMapper;
import java.nio.file.*;
import java.time.*;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.Environment;
import org.apache.ibatis.session.*;
import org.apache.ibatis.transaction.jdbc.JdbcTransactionFactory;
import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.Test;

class HrSpecialMarksPersistenceTest {
  @Test
  void distinct_confirmation_is_tenant_and_fact_version_bound() throws Exception {
    var ds = new JdbcDataSource();
    ds.setURL("jdbc:h2:mem:marks_" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1");
    try (var c = ds.getConnection();
        var st = c.createStatement()) {
      for (String sql :
          Files.readString(Path.of("../sql/migration/V1.2.12__hr_distinct_confirmations.sql"))
              .replace("\uFEFF", "")
              .split(";")) if (!sql.isBlank()) st.execute(sql);
    }
    var cfg = new Configuration(new Environment("test", new JdbcTransactionFactory(), ds));
    cfg.setMapUnderscoreToCamelCase(true);
    cfg.addMapper(HrSpecialMarksMapper.class);
    try (var xml =
        Files.newInputStream(Path.of("src/main/resources/mapper/hr/HrCandidateMapper.xml"))) {
      new XMLMapperBuilder(xml, cfg, "candidate", cfg.getSqlFragments()).parse();
    }
    try (var xml =
        Files.newInputStream(Path.of("src/main/resources/mapper/hr/HrSpecialMarksMapper.xml"))) {
      new XMLMapperBuilder(xml, cfg, "marks", cfg.getSqlFragments()).parse();
    }
    try (var session = new SqlSessionFactoryBuilder().build(cfg).openSession(true)) {
      var m = session.getMapper(HrSpecialMarksMapper.class);
      var pair = new HrSpecialMarksMapper.Pair("t", "a", "b", 1, 2);
      assertFalse(m.distinct(pair));
      m.confirm(pair, "u", "cipher", Instant.now());
      assertTrue(m.distinct(pair));
      assertFalse(m.distinct(new HrSpecialMarksMapper.Pair("t", "a", "b", 2, 2)));
      assertFalse(m.distinct(new HrSpecialMarksMapper.Pair("other", "a", "b", 1, 2)));
      m.deleteForSource("t", "a");
      assertFalse(m.distinct(pair));
    }
  }
}

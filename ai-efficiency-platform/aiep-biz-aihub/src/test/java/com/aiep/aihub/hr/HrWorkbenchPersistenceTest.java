package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;

import com.aiep.aihub.repository.hr.HrWorkbenchMapper;
import java.io.InputStream;
import java.nio.file.*;
import java.time.Instant;
import java.util.Set;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.Environment;
import org.apache.ibatis.session.*;
import org.apache.ibatis.transaction.jdbc.JdbcTransactionFactory;
import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.Test;

class HrWorkbenchPersistenceTest {
  @Test
  void statistics_exclude_expired_candidates_and_unauthorized_departments() throws Exception {
    var ds = new JdbcDataSource();
    ds.setURL("jdbc:h2:mem:workbench_" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1");
    try (var c = ds.getConnection();
        var st = c.createStatement()) {
      for (String sql :
          Files.readString(
                  Path.of("../sql/migration/V1.2.0__hr_positions_candidates_and_matching.sql"))
              .split(";")) if (!sql.isBlank()) st.execute(sql);
      st.execute(
          "INSERT INTO"
              + " ai_hr_candidate(id,tenant_id,department_id,current_snapshot_id,version,status,expires_at)"
              + " VALUES('valid','t','d','s',1,'ACTIVE','2030-01-01'),('expired','t','d','s',1,'ACTIVE','2020-01-01'),('private','t','other','s',1,'ACTIVE','2030-01-01')");
    }
    var configuration =
        new Configuration(new Environment("test", new JdbcTransactionFactory(), ds));
    configuration.setMapUnderscoreToCamelCase(true);
    configuration.addMapper(HrWorkbenchMapper.class);
    try (InputStream xml =
        Files.newInputStream(Path.of("src/main/resources/mapper/hr/HrWorkbenchMapper.xml"))) {
      new XMLMapperBuilder(xml, configuration, "workbench", configuration.getSqlFragments())
          .parse();
    }
    try (var session = new SqlSessionFactoryBuilder().build(configuration).openSession(true)) {
      var mapper = session.getMapper(HrWorkbenchMapper.class);
      var now = Instant.parse("2026-11-11T00:00:00Z");
      assertEquals(1, mapper.counts("t", Set.of("d"), now).candidates());
      assertEquals(0, mapper.counts("other", Set.of("d"), now).candidates());
      assertTrue(mapper.positions("t", Set.of("d"), now).isEmpty());
    }
  }
}

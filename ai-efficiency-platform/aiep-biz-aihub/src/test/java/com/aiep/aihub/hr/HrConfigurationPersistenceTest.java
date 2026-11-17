package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrDictionaryContracts.*;
import com.aiep.aihub.application.hr.*;
import com.aiep.aihub.repository.hr.*;
import com.fasterxml.jackson.databind.json.JsonMapper;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.Environment;
import org.apache.ibatis.session.*;
import org.apache.ibatis.transaction.jdbc.JdbcTransactionFactory;
import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.Test;

class HrConfigurationPersistenceTest {
  @Test
  void sql_versions_cas_import_and_tenant_scope_are_real() throws Exception {
    var ds = new JdbcDataSource();
    ds.setURL("jdbc:h2:mem:config_" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1");
    try (var c = ds.getConnection();
        var st = c.createStatement()) {
      for (String sql :
          Files.readString(Path.of("../sql/migration/V1.2.1__hr_configuration_extensions.sql"))
              .split(";")) if (!sql.isBlank()) st.execute(sql);
    }
    var configuration =
        new Configuration(new Environment("test", new JdbcTransactionFactory(), ds));
    configuration.setMapUnderscoreToCamelCase(true);
    configuration.addMapper(HrSettingsMapper.class);
    try (InputStream xml =
        Files.newInputStream(Path.of("src/main/resources/mapper/hr/HrSettingsMapper.xml"))) {
      new XMLMapperBuilder(xml, configuration, "hr-settings", configuration.getSqlFragments())
          .parse();
    }
    try (var session = new SqlSessionFactoryBuilder().build(configuration).openSession(false)) {
      var mapper = session.getMapper(HrSettingsMapper.class);
      var repository =
          new HrSettingsRepository(mapper, JsonMapper.builder().findAndAddModules().build());
      var service = new HrDictionaryService(repository);
      var actor =
          new HrActor(
              "t",
              "1",
              Set.of("d"),
              Set.of("hr:config:read", "hr:config:edit", "hr:config:publish"));
      var entry = new Entry("java", "SKILL", "Java", List.of("JDK"), "");
      var draft = service.save(actor, new Save("d", 0, List.of(entry)));
      assertEquals(1, draft.version());
      var published = service.publish(actor, "d", 1);
      assertEquals(2, published.version());
      assertEquals(
          "Java", service.normalize(actor, new Normalize("d", "SKILL", "JDK", "")).canonical());
      var changed = new Entry("java", "SKILL", "Java21", List.of("JDK"), "");
      service.save(actor, new Save("d", 2, List.of(changed)));
      assertEquals(
          "Java", service.normalize(actor, new Normalize("d", "SKILL", "JDK", "")).canonical());
      assertEquals("Java", service.versions(actor, "d").get(1).entries().getFirst().canonical());
      var preview = service.preflight(actor, new Save("d", 3, List.of(changed)));
      service.save(actor, new Save("d", 3, List.of(entry)));
      assertThrows(HrBusinessException.class, () -> service.adopt(actor, preview.id(), 1));
      assertEquals(4, service.get(actor, "d").version());
      var invalid =
          service.preflight(
              actor,
              new Save(
                  "d", 4, List.of(entry, new Entry("jvm", "SKILL", "Other", List.of("JDK"), ""))));
      assertFalse(invalid.conflicts().isEmpty());
      assertThrows(HrBusinessException.class, () -> service.adopt(actor, invalid.id(), 1));
      assertEquals(4, service.get(actor, "d").version());
      var other = new HrActor("other", "1", Set.of("d"), actor.permissions());
      assertEquals(0, service.get(other, "d").version());
      assertThrows(
          HrBusinessException.class,
          () ->
              repository.find(
                  new HrActor("t", "1", Set.of("x"), actor.permissions()), "DICTIONARY", "d"));
      assertFalse(repository.audits(actor).isEmpty());
      session.rollback();
      assertNull(mapper.find("t", "DICTIONARY", "d"));
    }
  }
}

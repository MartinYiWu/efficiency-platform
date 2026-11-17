package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.*;
import org.junit.jupiter.api.Test;

class HrTalentInterviewPersistenceTest {
  @Test
  void migration_has_durable_sources_grants_saga_and_immutable_versions() throws Exception {
    var path = Path.of("../sql/migration/V1.2.2__hr_talent_interview_extensions.sql");
    assertTrue(Files.exists(path), "talent/interview migration required");
    String ddl = Files.readString(path);
    for (String table :
        new String[] {
          "ai_hr_candidate_merge",
          "ai_hr_candidate_source",
          "ai_hr_interview_set",
          "ai_hr_interview_assignment",
          "ai_hr_contact_grant",
          "ai_hr_deletion_job",
          "ai_hr_audit",
          "ai_hr_interview_export"
        }) assertTrue(ddl.contains("CREATE TABLE " + table), table);
  }

  @Test
  void interviewer_projection_physically_omits_restricted_properties() throws Exception {
    var type = Class.forName("com.aiep.aihub.api.hr.HrInterviewContracts$InterviewGuide");
    for (var component : type.getRecordComponents())
      assertFalse(component.getName().matches("(?i).*(score|band|rank|contact|strength).*"));
  }
}

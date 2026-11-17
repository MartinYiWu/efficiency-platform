package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;

import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.application.hr.InterviewViewAssembler;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrInterviewProjectionTest {
  @Test
  void cleaned_attachment_excludes_identity_contact_badges_and_forbidden_attributes() {
    List<StructuredFact> facts =
        List.of(
            new StructuredFact(
                "a", "project", "负责订单模块", List.of(), null, null, null, null, null, null, null,
                null),
            new StructuredFact(
                "b", "skill", "Java 强", List.of(), null, null, null, null, null, null, null, null),
            new StructuredFact(
                "c",
                "project",
                "邮箱 a@example.test",
                List.of(),
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null),
            new StructuredFact(
                "d", "project", "婚育信息", List.of(), null, null, null, null, null, null, null, null));
    var snapshot =
        new Facts(
            "c",
            "r",
            "resume",
            1,
            100,
            "READY",
            new Profile("姓名", "本科", 12, ""),
            List.of(),
            List.of(),
            List.of(),
            0,
            0,
            1,
            facts);
    var attachment = new InterviewViewAssembler().resume(snapshot);
    assertEquals(1, attachment.size());
    assertEquals("负责订单模块", attachment.getFirst().text());
  }
}

package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.application.hr.*;
import com.aiep.aihub.repository.hr.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class HrResumeReuseServiceTest {
  final ObjectMapper json = new ObjectMapper().findAndRegisterModules();
  final HrResumeReuseMapper mapper = mock(HrResumeReuseMapper.class);
  final HrSensitiveJsonCodec codec =
      new HrSensitiveJsonCodec(Base64.getEncoder().encodeToString(new byte[32]));

  @ParameterizedTest
  @CsvSource({"renamed.txt,true", "renamed.TXT,true", "mislabelled.pdf,false", "mislabelled.docx,false"})
  void reuse_requires_original_format_and_original_parse(String filename, boolean eligible) throws Exception {
    var facts = new HrMatchingLifecycleTest().facts();
    var actor = new HrActor("t", "1", Set.of("d"), Set.of("hr:candidate:read"));
    when(mapper.find(eq("t"), eq("d"), eq("a".repeat(64)), anySet(), any()))
        .thenReturn(
            List.of(
                new HrResumeReuseMapper.Row(
                    "c",
                    "d",
                    "ACTIVE",
                    Instant.now().plusSeconds(100),
                    "TALENT_POOL",
                    1,
                    codec.seal(json.writeValueAsString(facts)),
                    codec.seal("{\"blocks\":[],\"identity\":{}}"))));
    var result = new HrResumeReuseService(mapper, codec, json).find(actor, "d", "a".repeat(64), filename);
    if (!eligible) {
      assertNull(result);
      return;
    }
    assertNotNull(result);
    assertEquals(1, result.originalFacts().version());
    assertTrue(result.extraction().path("blocks").isArray());
  }

  @Test
  void hidden_or_expired_sources_never_reuse_or_expose_metadata() throws Exception {
    var actor =
        new HrActor(
            "t",
            "1",
            Set.of("d"),
            Set.of("hr:candidate:read"),
            Set.of(),
            Set.of("allowed"),
            true,
            List.of(new HrActor.GrantScope("hr:candidate:read", "d", null, "allowed")));
    var rows =
        List.of(
            new HrResumeReuseMapper.Row(
                "hidden",
                "d",
                "ACTIVE",
                Instant.now().plusSeconds(100),
                "TALENT_POOL",
                1,
                "invalid",
                "invalid"),
            new HrResumeReuseMapper.Row(
                "allowed",
                "d",
                "ACTIVE",
                Instant.now().minusSeconds(1),
                "TALENT_POOL",
                1,
                "invalid",
                "invalid"),
            new HrResumeReuseMapper.Row(
                "allowed",
                "d",
                "ACTIVE",
                Instant.now().plusSeconds(100),
                "TALENT_POOL",
                2,
                "invalid",
                "invalid"));
    when(mapper.find(eq("t"), eq("d"), anyString(), eq(Set.of("allowed")), any())).thenReturn(rows);
    assertNull(new HrResumeReuseService(mapper, codec, json).find(actor, "d", "a".repeat(64), "resume.txt"));
  }

  @Test
  void no_source_read_permission_falls_back_to_fresh_parse_without_query() {
    var actor = new HrActor("t", "1", Set.of("d"), Set.of("hr:candidate:upload"));
    assertNull(new HrResumeReuseService(mapper, codec, json).find(actor, "d", "a".repeat(64), "resume.txt"));
    verifyNoInteractions(mapper);
  }
}

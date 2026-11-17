package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrTalentSemanticContracts.*;
import com.aiep.aihub.application.hr.*;
import com.aiep.aihub.repository.hr.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrTalentSemanticServiceTest {
  @Test
  void polling_completed_search_rechecks_source_without_any_gateway_call() throws Exception {
    var jobs = mock(HrTalentSemanticMapper.class);
    var mapper = mock(HrTalentMapper.class);
    var talent = mock(HrTalentSearchService.class);
    var gateway = mock(HrSemanticGateway.class);
    var codec = mock(HrSensitiveJsonCodec.class);
    var json = new ObjectMapper().findAndRegisterModules();
    var authority = mock(HrActorAuthority.class);
    var service =
        new HrTalentSemanticService(
            jobs,
            mapper,
            talent,
            gateway,
            authority,
            codec,
            json,
            mock(org.springframework.transaction.PlatformTransactionManager.class));
    var actor = new HrActor("t", "u", Set.of("d"), Set.of("hr:candidate:read"));
    var source =
        new HrTalentSemanticService.FrozenSource(
            "c",
            "snapshot",
            "hash",
            "hr-search-stable",
            List.of(new HrTalentSemanticService.SafeBlock("b", "Java")));
    var frozen = new HrTalentSemanticService.FrozenSearch("Java", List.of(source), "budget");
    var view =
        new SearchJob(
            "j",
            "SUCCEEDED",
            "Java",
            List.of(new Hit("c", 0.8, List.of(new Match("b", 0, 4, "Java")), "SUCCEEDED", null)),
            Instant.now());
    when(codec.open("input")).thenReturn(json.writeValueAsString(frozen));
    when(codec.open("result")).thenReturn(json.writeValueAsString(view));
    when(jobs.find("t", "j"))
        .thenReturn(
            new HrTalentSemanticMapper.Row(
                "j",
                "t",
                "u",
                "SUCCEEDED",
                "input",
                "result",
                "key",
                "hash",
                Instant.now(),
                Instant.now()));
    when(talent.authorized(actor, "c", "hr:candidate:read"))
        .thenReturn(new HrCandidateContracts.Candidate("c", "t", "d", "snapshot", 1));
    assertEquals("SUCCEEDED", service.get(actor, "j").status());
    verify(talent).purpose(any(), any(), eq("TALENT_POOL"));
    verifyNoInteractions(gateway);
  }

  @Test
  void unconfirmed_post_never_reserves_budget() {
    var gateway = mock(HrSemanticGateway.class);
    var service =
        new HrTalentSemanticService(
            mock(HrTalentSemanticMapper.class),
            mock(HrTalentMapper.class),
            mock(HrTalentSearchService.class),
            gateway,
            mock(HrActorAuthority.class),
            mock(HrSensitiveJsonCodec.class),
            new ObjectMapper(),
            mock(org.springframework.transaction.PlatformTransactionManager.class));
    var actor = new HrActor("t", "u", Set.of("d"), Set.of("hr:candidate:read"));
    assertThrows(
        HrBusinessException.class,
        () -> service.create(actor, new SearchRequest("Java", false, null), "search-key"));
    verifyNoInteractions(gateway);
  }
}

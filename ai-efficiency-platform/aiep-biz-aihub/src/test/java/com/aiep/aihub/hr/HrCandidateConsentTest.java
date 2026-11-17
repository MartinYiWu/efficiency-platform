package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.application.hr.*;
import com.aiep.aihub.repository.hr.HrBatchMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrCandidateConsentTest {
  final HrCandidateRepositoryPort repository = mock(HrCandidateRepositoryPort.class);
  final HrBatchMapper policies = mock(HrBatchMapper.class);
  final HrSemanticGateway gateway = mock(HrSemanticGateway.class);
  final ObjectMapper json = new ObjectMapper();
  final HrCandidateService service =
      new HrCandidateService(
          repository,
          json,
          new HrSensitiveJsonCodec(Base64.getEncoder().encodeToString(new byte[32])),
          gateway,
          policies);
  final HrActor actor =
      new HrActor("t", "1", Set.of("d"), Set.of("hr:candidate:upload", "hr:candidate:read"));

  ImportResume request(String version) {
    return new ImportResume(
        "d",
        "synthetic.txt",
        Base64.getEncoder().encodeToString("synthetic".getBytes()),
        true,
        version);
  }

  @Test
  void arbitraryConsentVersionCannotTriggerAgent() {
    assertThrows(
        HrBusinessException.class, () -> service.importResume(actor, request("fabricated")));
    verifyNoInteractions(gateway);
  }

  @Test
  void validPublishedPolicyFreezesRetentionDeadline() throws Exception {
    var policy = new HrBatchContracts.Policy("policy", "合成授权文本", 12, 3, 3, 7, 80, 65, 50, 1);
    when(policies.latestPolicy("t"))
        .thenReturn(
            new HrBatchMapper.PolicyRow(
                "policy", "t", json.writeValueAsString(policy), 1, Instant.now()));
    when(gateway.execute(eq(actor), eq(6101L), anyString(), any()))
        .thenReturn(
            json.readTree(
                "{\"content_hash\":\"b3cc0475bb78a5026098858e9889acf666d31062d513d303314eca31d36e72f2\",\"cleaned_blocks\":[{\"block_id\":\"b\",\"text\":\"合成工作事实\"}],\"identity\":{\"name\":{\"value\":\"合成测试\"}}}"));
    when(gateway.execute(eq(actor), eq(6102L), anyString(), any()))
        .thenReturn(json.readTree("{\"facts\":[]}"));
    service.importResume(actor, request("policy"));
    verify(repository)
        .create(
            argThat(
                c ->
                    c.status().equals("ACTIVE")
                        && c.consentPolicyId().equals("policy")
                        && c.expiresAt()
                            .equals(
                                c.acquiredAt()
                                    .atZone(ZoneId.of("Asia/Shanghai"))
                                    .plusMonths(12)
                                    .toInstant())),
            any());
  }

  @Test
  void expiredCandidateCannotBeRead() {
    when(repository.find("t", "c"))
        .thenReturn(
            new Candidate(
                "c",
                "t",
                "d",
                "s",
                1,
                "policy",
                Instant.now().minusSeconds(100),
                Instant.now().minusSeconds(1),
                "ACTIVE"));
    assertThrows(HrBusinessException.class, () -> service.facts(actor, "c"));
    verify(repository, never()).snapshot(anyString(), anyString());
  }
}

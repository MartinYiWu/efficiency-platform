package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.application.hr.*;
import com.aiep.aihub.repository.hr.HrBatchMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrBatchUploadCapacityTest {
  private final HrBatchMapper mapper = mock(HrBatchMapper.class);
  private final HrMatchingService matching = mock(HrMatchingService.class);
  private final HrActor actor =
      new HrActor("t", "u", Set.of("d"), Set.of("hr:candidate:upload"));
  private final HrBatchService service =
      new HrBatchService(
          mapper,
          mock(HrPositionService.class),
          mock(HrCandidateService.class),
          matching,
          mock(HrMatchingRunExecutor.class),
          new HrSensitiveJsonCodec(Base64.getEncoder().encodeToString(new byte[32])),
          new ObjectMapper().findAndRegisterModules());

  private byte[] fullBatch() throws Exception {
    byte[] content = "合成容量验收Java".getBytes(StandardCharsets.UTF_8);
    String hash =
        HexFormat.of()
            .formatHex(
                MessageDigest.getInstance("SHA-256")
                    .digest(new ObjectMapper().writeValueAsBytes(Base64.getEncoder().encodeToString(content))));
    when(mapper.lockBatch("t", "b"))
        .thenReturn(
            new HrBatchMapper.BatchRow(
                "b", "t", "d", "u", null, "STORE_ONLY", "policy", 1, "DRAFT", 1,
                Instant.now(), "request-key", "request-hash"));
    when(mapper.items("t", "b"))
        .thenReturn(
            List.of(
                new HrBatchMapper.ItemRow(
                    "existing", "t", "b", "resume.txt", "sealed", hash,
                    "PENDING", "UPLOADED", null, null, 0)));
    return content;
  }

  @Test
  void same_content_at_full_capacity_returns_existing_item_without_insert_or_model() throws Exception {
    var content = fullBatch();
    var item = service.upload(actor, "b", "renamed.txt", content);
    assertEquals("existing", item.id());
    assertEquals("resume.txt", item.filename());
    verify(mapper, never()).addItem(any());
    verifyNoInteractions(matching);
  }

  @Test
  void different_content_at_full_capacity_is_still_rejected() throws Exception {
    fullBatch();
    assertThrows(
        HrBusinessException.class,
        () -> service.upload(actor, "b", "different.txt", "different Java".getBytes(StandardCharsets.UTF_8)));
    verify(mapper, never()).addItem(any());
    verifyNoInteractions(matching);
  }
}

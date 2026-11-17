package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.api.hr.HrBatchContracts.*;
import com.aiep.aihub.application.hr.*;
import com.aiep.aihub.repository.hr.HrBatchMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Set;
import org.junit.jupiter.api.Test;

class HrBatchPolicyTest {
    private final HrActor actor = new HrActor("tenant", "1", Set.of("department"), Set.of("hr:settings:edit", "hr:candidate:upload", "hr:candidate:read"));
    private final HrBatchMapper mapper = mock(HrBatchMapper.class);
    private final ObjectMapper json = new ObjectMapper().findAndRegisterModules();
    private final HrBatchService service = new HrBatchService(mapper, mock(HrPositionService.class), mock(HrCandidateService.class),
            mock(HrMatchingService.class), mock(HrMatchingRunExecutor.class), new HrSensitiveJsonCodec(java.util.Base64.getEncoder().encodeToString(new byte[32])), json);

    @Test void no_policy_cannot_claim_authorization_or_start_upload() {
        assertThrows(HrBusinessException.class, () -> service.create(actor,
                new CreateBatch(null, "STORE_ONLY", "invented", true, 1, "department"), "a-valid-request-key"));
        verify(mapper, never()).insertBatch(any());
    }

    @Test void policy_requires_notice_and_refuses_unsafe_attempt_limit() {
        assertThrows(HrBusinessException.class, () -> service.publishPolicy(actor, new Policy("draft", " ", 12, 3, 3, 30, 80, 65, 50, 0)));
        assertThrows(HrBusinessException.class, () -> service.publishPolicy(actor, new Policy("draft", "仅供授权招聘评估", 12, 3, 4, 30, 80, 65, 50, 0)));
    }

    @Test void upload_without_explicit_consent_is_rejected_before_saving() {
        assertThrows(HrBusinessException.class, () -> service.create(actor, new CreateBatch(null, "STORE_ONLY", "p1", false, 1, "department"), "a-valid-request-key"));
        verify(mapper, never()).insertBatch(any());
    }

    @Test void unconfirmed_remote_stop_is_reported_as_pending_not_success() {
        var row=new HrBatchMapper.BatchRow("b","tenant","department","1",null,"STORE_ONLY","policy",1,"RUNNING",2,java.time.Instant.now(),"key-12345","hash");
        var item=new HrBatchMapper.ItemRow("i","tenant","b","synthetic.txt","sealed","hash","RUNNING","EXTRACTING",null,null,10);
        when(mapper.batch("tenant","b")).thenReturn(row);when(mapper.items("tenant","b")).thenReturn(java.util.List.of(item));
        service.cancel(actor,"b");
        verify(mapper).pendingCancel("tenant","b");
        verify(mapper).itemState("tenant","i","CANCELLED","CANCEL_PENDING","CANCEL_PENDING",null,"HR_CANCEL_NOT_CONFIRMED",100);
    }
}

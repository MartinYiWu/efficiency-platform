package com.aiep.platformai.api.dto;

import static org.junit.jupiter.api.Assertions.*;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

class MemoryRefreshContractTest {
    private final ObjectMapper mapper = new ObjectMapper().disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
    private ObjectNode fixture() throws Exception {
        return (ObjectNode) mapper.readTree(Files.readString(Path.of("../../efficiency-platform-agent/tests/fixtures/memory_refresh_transport.json")));
    }
    @Test void sharedGoldenPreservesEveryFieldAndFingerprint() throws Exception {
        var data = fixture();
        for (var entry : new Object[][] {{"wait", MemoryContextWait.class}, {"resume", MemoryResumeRequest.class}, {"receipt", MemoryResumeReceipt.class}}) {
            var raw = data.get((String)entry[0]);
            var parsed = mapper.treeToValue(raw, (Class<?>)entry[1]);
            assertEquals(raw, mapper.readTree(mapper.writeValueAsString(parsed)));
        }
        var request = mapper.treeToValue(data.get("resume"), MemoryResumeRequest.class);
        assertEquals(data.path("canonical_resume_sha256").asText(), request.canonicalFingerprint());
    }
    @Test void rejectsCoercionUnknownFieldsAndModeSmuggling() throws Exception {
        for (String field : new String[]{"attempt", "packet_revision", "expected_execution_revision"}) {
            var raw = fixture().withObject("/resume"); raw.put(field, true);
            assertThrows(Exception.class, () -> mapper.treeToValue(raw, MemoryResumeRequest.class));
            raw.put(field, "1");
            assertThrows(Exception.class, () -> mapper.treeToValue(raw, MemoryResumeRequest.class));
        }
        for (String mode : new String[]{"cpu", "paid", "REFRESH"}) {
            var raw = fixture().withObject("/resume"); raw.put("mode", mode);
            assertThrows(Exception.class, () -> mapper.treeToValue(raw, MemoryResumeRequest.class));
        }
        var raw = fixture().withObject("/resume"); raw.put("max_cost_cny", 1000);
        assertThrows(Exception.class, () -> mapper.treeToValue(raw, MemoryResumeRequest.class));
        raw.remove("max_cost_cny"); raw.withObject("/refreshed_context").put("unexpected", true);
        assertThrows(Exception.class, () -> mapper.treeToValue(raw, MemoryResumeRequest.class));
    }
    @Test void rejectsMissingNullFieldsAndInvalidWaitPhase() throws Exception {
        var missing = fixture().withObject("/wait"); missing.remove("stage_id");
        assertThrows(Exception.class, () -> mapper.treeToValue(missing, MemoryContextWait.class));
        var invalid = fixture().withObject("/wait"); invalid.putNull("canonical_request_hmac");
        assertThrows(Exception.class, () -> mapper.treeToValue(invalid, MemoryContextWait.class));
    }
    @Test void legacyConstructorRetainsSevenFieldWireAndCannotBeV2() {
        var legacy = new MemoryResumeRequest("wait", 1, 1, "resume", "hash", "refresh", false);
        var json = mapper.valueToTree(legacy);
        assertEquals(7, json.size());
        assertFalse(legacy.isV2());
        assertThrows(IllegalStateException.class, legacy::requireV2);
    }
    @Test void rejectsInconsistentSuccessAndExpiredReceipt() throws Exception {
        var raw = fixture().withObject("/receipt"); raw.put("candidate_phase", "PENDING");
        assertThrows(Exception.class, () -> mapper.treeToValue(raw, MemoryResumeReceipt.class));
        raw.put("code", "MEMORY_REFRESH_PACKET_EXPIRED"); raw.put("candidate_phase", "APPLIED_EXPIRED");
        assertThrows(Exception.class, () -> mapper.treeToValue(raw, MemoryResumeReceipt.class));
    }
    @Test void nullableBeforePrepareNoneCpuAndPaidRoundTripAndFingerprint() throws Exception {
        var data=fixture();
        var wait=mapper.treeToValue(data.get("nullable_wait"),MemoryContextWait.class);
        assertEquals(data.get("nullable_wait"),mapper.readTree(mapper.writeValueAsString(wait)));
        for(String name:new String[]{"cpu_resume","paid_resume"}) {
            var command=mapper.treeToValue(data.get(name),MemoryResumeRequest.class);
            assertEquals(data.get(name),mapper.readTree(mapper.writeValueAsString(command)));
            assertEquals(data.get(name+"_sha256").asText(),command.canonicalFingerprint());
            command.validateBinding(wait,wait.scope(),wait.executionId(),"d".repeat(64),null);
        }
        var receipt=mapper.treeToValue(data.get("cpu_receipt"),MemoryResumeReceipt.class);
        assertEquals(data.get("cpu_receipt"),mapper.readTree(mapper.writeValueAsString(receipt)));
    }
    @Test void candidatePhaseCannotDescribeAnotherResult() throws Exception {
        var raw=fixture().withObject("/receipt"); raw.put("code","SOURCE_CHANGED"); raw.put("dispatch_allowed",false);
        assertThrows(Exception.class,()->mapper.treeToValue(raw,MemoryResumeReceipt.class));
        var missingNext=fixture().withObject("/receipt"); missingNext.put("code","MEMORY_REFRESH_PACKET_EXPIRED");
        missingNext.put("candidate_phase","APPLIED_EXPIRED"); missingNext.put("state","WAITING_CONTEXT"); missingNext.put("dispatch_allowed",false);
        assertThrows(Exception.class,()->mapper.treeToValue(missingNext,MemoryResumeReceipt.class));
    }
    @Test void strictlyRejectsFloatsBadLengthsAndBoundScope() throws Exception {
        for(String field:new String[]{"attempt","packet_revision"}) {
            var raw=fixture().withObject("/resume"); raw.put(field,1.0);
            assertThrows(Exception.class,()->mapper.treeToValue(raw,MemoryResumeRequest.class));
        }
        for(String value:new String[]{"c".repeat(63),"z".repeat(64)}) {
            var raw=fixture().withObject("/resume"); raw.put("canonical_request_hmac",value);
            assertThrows(Exception.class,()->mapper.treeToValue(raw,MemoryResumeRequest.class));
        }
        var longId=fixture().withObject("/resume"); longId.put("resume_request_id","😀".repeat(129));
        assertThrows(Exception.class,()->mapper.treeToValue(longId,MemoryResumeRequest.class));
        longId.put("resume_request_id","😀".repeat(128));
        assertEquals(128,mapper.treeToValue(longId,MemoryResumeRequest.class).resumeRequestId().codePointCount(0,256));
        var data=fixture(); var wait=mapper.treeToValue(data.get("wait"),MemoryContextWait.class);
        var command=mapper.treeToValue(data.get("resume"),MemoryResumeRequest.class);
        var original=mapper.treeToValue(data.get("original_context"),MemoryContextEnvelope.class);
        command.validateBinding(wait,wait.scope(),wait.executionId(),"d".repeat(64),original);
        for(String dimension:new String[]{"tenant_id","user_id","domain","top_level_agent_id","session_kind","session_id"}) {
            ObjectNode scope=mapper.valueToTree(wait.scope());
            if(dimension.equals("domain")||dimension.equals("top_level_agent_id")) { scope.put("domain","hr"); scope.put("top_level_agent_id","hr"); }
            else if(dimension.equals("session_kind")) { scope.put("session_kind","TASK_ONLY"); scope.putNull("session_id"); }
            else scope.put(dimension,"other");
            var route=mapper.treeToValue(scope,MemoryContextEnvelope.Scope.class);
            assertThrows(IllegalArgumentException.class,()->command.validateBinding(wait,route,wait.executionId(),"d".repeat(64),original));
        }
    }
    @Test void operationAttemptRevisionsAndDeadlineUseTheirActualDomain() throws Exception {
        for(String name:new String[]{"wait","resume"}) {
            Class<?> target=name.equals("wait")?MemoryContextWait.class:MemoryResumeRequest.class;
            for(int attempt:new int[]{0,4}) {
                var raw=fixture().withObject("/"+name); raw.put("attempt",attempt);
                assertThrows(Exception.class,()->mapper.treeToValue(raw,target));
            }
            String[] fields=name.equals("wait")?new String[]{"expected_packet_revision","expected_execution_revision","original_deadline"}:new String[]{"packet_revision","expected_execution_revision"};
            for(String field:fields) {
                var raw=fixture().withObject("/"+name); raw.put(field,0);
                assertThrows(Exception.class,()->mapper.treeToValue(raw,target));
            }
        }
    }
    @Test void officialGraphRootNamespaceIsEmptyButNotNull() throws Exception {
        var raw=fixture().withObject("/wait"); raw.put("checkpoint_ns","");
        assertEquals("",mapper.treeToValue(raw,MemoryContextWait.class).checkpointNs());
        raw.putNull("checkpoint_ns");
        assertThrows(Exception.class,()->mapper.treeToValue(raw,MemoryContextWait.class));
    }
    @Test void waitExposesTheExactCurrentFingerprintAndRejectsCorruption() throws Exception {
        var raw=fixture().withObject("/wait");
        var wait=mapper.treeToValue(raw,MemoryContextWait.class);
        assertEquals("d".repeat(64),mapper.valueToTree(wait).path("expected_current_context_fingerprint").asText());
        raw.put("expected_current_context_fingerprint","bad");
        assertThrows(Exception.class,()->mapper.treeToValue(raw,MemoryContextWait.class));
        var data=fixture(); var changedRaw=data.withObject("/wait"); changedRaw.put("expected_current_context_fingerprint","f".repeat(64));
        var changedWait=mapper.treeToValue(changedRaw,MemoryContextWait.class);
        var command=mapper.treeToValue(data.get("resume"),MemoryResumeRequest.class);
        var original=mapper.treeToValue(data.get("original_context"),MemoryContextEnvelope.class);
        assertThrows(IllegalArgumentException.class,()->command.validateBinding(changedWait,changedWait.scope(),changedWait.executionId(),"d".repeat(64),original));
    }
    @Test void reviewReceiptRejectsNonPositiveNonNullRevisions() throws Exception {
        for(String field:new String[]{"packet_revision","execution_revision","current_packet_revision"}) {
            var raw=fixture().withObject("/receipt"); raw.put("code","SOURCE_CHANGED"); raw.putNull("candidate_phase"); raw.put("state","BLOCKED"); raw.put("dispatch_allowed",false); raw.put(field,0);
            assertThrows(Exception.class,()->mapper.treeToValue(raw,MemoryResumeReceipt.class));
        }
        var zero=fixture().withObject("/receipt"); zero.put("packet_revision",0); zero.put("execution_revision",0); zero.put("current_packet_revision",0);
        assertThrows(Exception.class,()->mapper.treeToValue(zero,MemoryResumeReceipt.class));
    }
    @Test void reviewEveryAcceptedCandidateNeedsConsumedCountAndDistinctSuccessor() throws Exception {
        for(String phase:new String[]{"ACKED","PENDING","EXPIRED_UNAPPLIED","APPLIED_EXPIRED","ABORTED"}) {
            var raw=fixture().withObject("/receipt"); raw.put("candidate_phase",phase);
            switch(phase) {
                case "PENDING" -> { raw.put("code","MEMORY_REFRESH_PENDING"); raw.put("state","REFRESH_PENDING"); raw.put("dispatch_allowed",false); raw.put("current_packet_revision",1); }
                case "EXPIRED_UNAPPLIED" -> { raw.put("code","MEMORY_REFRESH_PACKET_EXPIRED"); raw.put("state","WAITING_CONTEXT"); raw.put("dispatch_allowed",false); raw.put("current_packet_revision",1); }
                case "APPLIED_EXPIRED" -> { raw.put("code","MEMORY_REFRESH_PACKET_EXPIRED"); raw.put("state","WAITING_CONTEXT"); raw.put("dispatch_allowed",false); raw.put("next_wait_event_id","next"); }
                case "ABORTED" -> { raw.put("code","SOURCE_CHANGED"); raw.put("state","REVOKED"); raw.put("dispatch_allowed",false); }
                default -> { }
            }
            raw.put("refresh_count",0);
            assertThrows(Exception.class,()->mapper.treeToValue(raw,MemoryResumeReceipt.class),phase);
            raw.put("refresh_count",1);
            assertEquals(1,mapper.treeToValue(raw,MemoryResumeReceipt.class).refreshCount());
        }
        var successor=fixture().withObject("/receipt"); successor.put("code","MEMORY_REFRESH_PACKET_EXPIRED"); successor.put("candidate_phase","APPLIED_EXPIRED"); successor.put("state","WAITING_CONTEXT"); successor.put("dispatch_allowed",false); successor.put("next_wait_event_id",successor.get("wait_event_id").asText());
        assertThrows(Exception.class,()->mapper.treeToValue(successor,MemoryResumeReceipt.class));
        successor.put("next_wait_event_id","different-wait");
        assertEquals("different-wait",mapper.treeToValue(successor,MemoryResumeReceipt.class).nextWaitEventId());
    }
    @Test void reviewUnacceptedReceiptsKeepZeroCountAndNullUnknownRevisions() throws Exception {
        for(String code:new String[]{"CPU_CONFIRMED","CONTINUATION_AUTH_UNSUPPORTED","MEMORY_AUTHORITY_UNAVAILABLE"}) {
            var raw=fixture().withObject("/cpu_receipt"); raw.put("code",code); raw.put("refresh_count",0);
            for(String field:new String[]{"receipt_ref","wait_event_id","packet_revision","execution_revision","current_packet_revision","current_context_fingerprint"}) raw.putNull(field);
            assertEquals(0,mapper.treeToValue(raw,MemoryResumeReceipt.class).refreshCount());
        }
    }
    @Test void reviewSevenKnownLegacyResultsPreserveTwoFieldWireAndApprovedAliases() throws Exception {
        for(String code:new String[]{"CPU_CONFIRMED","MEMORY_THREAD_FENCED","EXPIRED","CONTINUATION_AUTH_UNSUPPORTED","MEMORY_REFRESH_LIMIT","MEMORY_REFRESH_AUTH_UNSUPPORTED","MEMORY_AUTHORITY_REFRESH_REQUIRED"}) {
            String expected=switch(code) { case "EXPIRED" -> "EXECUTION_EXPIRED"; case "MEMORY_REFRESH_LIMIT" -> "CONTEXT_REFRESH_LIMIT"; default -> code; };
            var raw=mapper.createObjectNode().put("code",code).put("receipt_ref","legacy-receipt");
            var receipt=mapper.treeToValue(raw,MemoryResumeReceipt.class);
            assertEquals(expected,receipt.code());
            var wire=mapper.readTree(mapper.writeValueAsString(receipt));
            assertEquals(2,wire.size()); assertEquals(expected,wire.get("code").asText()); assertNull(receipt.state()); assertNull(receipt.dispatchAllowed());
        }
        var unknown=mapper.createObjectNode().put("code","UNKNOWN_LEGACY_CODE").put("receipt_ref","legacy-receipt");
        assertThrows(Exception.class,()->mapper.treeToValue(unknown,MemoryResumeReceipt.class));
    }
    @Test void reviewLegacyOnlyCodesCannotEnterV2WireOrCanonicalConstructor() throws Exception {
        for(String code:new String[]{"MEMORY_THREAD_FENCED","MEMORY_REFRESH_AUTH_UNSUPPORTED","MEMORY_AUTHORITY_REFRESH_REQUIRED"}) {
            var raw=fixture().withObject("/cpu_receipt"); raw.put("code",code);
            assertThrows(Exception.class,()->mapper.treeToValue(raw,MemoryResumeReceipt.class));
            var value=MemoryResumeReceipt.Code.valueOf(code);
            assertThrows(IllegalArgumentException.class,()->new MemoryResumeReceipt(value,null,null,null,null,null,null,0L,MemoryResumeReceipt.State.BLOCKED,null,null,false));
        }
    }
}

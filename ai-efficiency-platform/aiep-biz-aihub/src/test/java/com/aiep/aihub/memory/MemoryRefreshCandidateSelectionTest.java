package com.aiep.aihub.memory;

import com.aiep.aihub.api.memory.*;
import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.repository.memory.*;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformai.api.dto.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

/** 仅验证本地选择策略；真实SQL锁、并发和HTTP另由受控MySQL IT证明。 */
class MemoryRefreshCandidateSelectionTest {
    final ObjectMapper json=new ObjectMapper();
    final MemoryRefreshMapper refresh=mock(MemoryRefreshMapper.class);
    final Map<String,MemoryRefreshMapper.Candidate> rows=new LinkedHashMap<>();
    final AtomicLong seconds=new AtomicLong(161);
    final MemoryScopeDTO scope;
    final MemoryContextWait wait;
    final MemoryPacketService service;
    MemoryRefreshCandidateSelectionTest()throws Exception {
        var fixture=json.readTree(Files.readString(Path.of("../../efficiency-platform-agent/tests/fixtures/memory_refresh_transport.json")));
        var old=json.treeToValue(fixture.get("original_context"),MemoryContextEnvelope.class);var p=old.packet();var a=old.authorization();
        var packet=new MemoryContextPacket(p.packetId(),p.packetRevision(),p.scope(),p.taskId(),p.executionId(),p.policyVersion(),p.executionRevision(),p.issuedAt(),p.expiresAt(),p.grantEpoch(),p.sourceEpoch(),p.deletionEpoch(),p.semanticInputHash(),p.parentAuthorizationRef(),List.of(),p.safetyDependencies());
        var envelope=new MemoryContextEnvelope(old.schemaVersion(),old.memoryMode(),old.scope(),packet,new MemoryAuthorization(a.policy(),a.executionGrants(),1000,MemoryPacketDigest.digest(packet),MemoryPacketDigest.semanticDigest(packet),a.requestDigest(),a.inputDependencies()));
        var s=envelope.scope();scope=new MemoryScopeDTO(s.tenantId(),s.userId(),s.domain(),s.topLevelAgentId(),s.sessionKind(),s.sessionId());
        var w=json.treeToValue(fixture.get("wait"),MemoryContextWait.class);
        wait=new MemoryContextWait(w.contractVersion(),w.waitEventId(),w.runtimeId(),w.taskId(),w.executionId(),w.scope(),w.expectedPacketRevision(),w.expectedExecutionRevision(),w.expectedCurrentContextFingerprint(),w.operationHash(),w.logicalOperationId(),w.semanticInputHash(),w.canonicalRequestHmac(),w.attempt(),w.stageId(),w.stageSlot(),w.checkpointMode(),w.checkpointNs(),w.checkpointId(),w.waitPhase(),1000,0);
        var row=new MemoryPacketMapper.PacketRow(b(s.tenantId()),b(p.executionId()),b(p.packetId()),p.packetRevision(),b(s.userId()),b(p.taskId()),json.writeValueAsString(s),json.writeValueAsString(a.policy()),json.writeValueAsString(a.executionGrants()),json.writeValueAsString(Map.of("schema_version","memory-packet-references/2","items",List.of(),"input_dependencies",a.inputDependencies())),json.writeValueAsString(p.safetyDependencies()),a.requestDigest(),envelope.authorization().packetDigest(),envelope.authorization().semanticSnapshotDigest(),p.semanticInputHash(),b(p.parentAuthorizationRef()),p.executionRevision(),p.grantEpoch(),p.sourceEpoch(),p.deletionEpoch(),1000,p.issuedAt(),p.expiresAt());
        var anchor=new MemoryRefreshMapper.Anchor(row.tenantId(),row.executionId(),row.userId(),row.packetId(),row.packetRevision(),row.executionRevision(),row.requestDigest(),row.semanticDigest(),1000,b("original-login"),60,900);
        var memory=mock(MemoryMapper.class);var packets=mock(MemoryPacketMapper.class);when(packets.findPacket(any(),any())).thenReturn(row);
        var published=new MemoryMapper.PolicyPO(b(a.policy().policyId()),b(a.policy().version()),"{\"artifacts\":{\"schema_version\":\"memory-artifacts/1\",\"index_mode\":\"NOT_PROVISIONED\",\"index_backends\":[]}}",null,"memory-policy/1");
        when(memory.findPolicyVersion(any(),any(),any())).thenReturn(published);when(memory.findPublishedPolicy(any(),any())).thenReturn(published);
        var identity=mock(IdentityFacade.class);when(identity.refresh(s.tenantId(),s.userId(),"original-login")).thenReturn(Optional.of(new IdentityFacade.Subject(s.tenantId(),s.userId(),Set.of(),Set.of(),Set.of(),Set.of(),List.of(),"original-login")));
        var dependencies=mock(MemoryDependencyService.class);when(dependencies.requireCurrent(any(),any())).thenReturn(Instant.ofEpochSecond(900));
        when(refresh.findAnchor(any(),any())).thenReturn(anchor);when(refresh.lockPacket(any(),any())).thenReturn(new MemoryRefreshMapper.PacketLockPO(row.executionId()));
        when(refresh.findCandidate(any(),any(),any())).thenAnswer(c->rows.get(text(c.getArgument(2))));
        when(refresh.findLatestForWait(any(),any(),any())).thenAnswer(c->rows.values().stream().filter(r->Arrays.equals(r.waitEventId(),c.getArgument(2))).reduce((x,y)->y).orElse(null));
        when(refresh.findPending(any(),any())).thenAnswer(c->rows.values().stream().filter(r->r.phase().equals("PREPARED")).findFirst().orElse(null));
        when(refresh.findCurrent(any(),any())).thenAnswer(c->rows.values().stream().filter(r->Set.of("ACKED","APPLIED_EXPIRED").contains(r.phase())).reduce((x,y)->y).orElse(null));
        when(refresh.highestRevision(any(),any())).thenAnswer(c->rows.values().stream().mapToLong(MemoryRefreshMapper.Candidate::targetRevision).max().orElse(0));
        when(refresh.countForWait(any(),any(),any())).thenAnswer(c->(int)rows.values().stream().filter(r->Arrays.equals(r.waitEventId(),c.getArgument(2))).count());
        when(refresh.maxConfirmedCount(any(),any())).thenAnswer(c->rows.values().stream().filter(r->r.refreshCount()!=null).mapToInt(r->r.refreshCount().intValue()).max().orElse(0));
        when(refresh.insertCandidate(any(),any())).thenAnswer(c->{MemoryRefreshMapper.Candidate r=c.getArgument(1);rows.put(text(r.resumeRequestId()),r);return 1;});
        when(refresh.complete(any(),any())).thenAnswer(c->{MemoryRefreshMapper.Candidate r=c.getArgument(0);MemoryResumeReceipt receipt=c.getArgument(1);
            rows.put(text(r.resumeRequestId()),new MemoryRefreshMapper.Candidate(r.tenantId(),r.executionId(),r.resumeRequestId(),r.waitEventId(),r.oldPacketRevision(),r.targetRevision(),r.expectedCurrentContextFingerprint(),r.requestHash(),r.candidateDigest(),r.issuedAt(),r.expiresAt(),receipt.candidatePhase().name(),receipt.code(),b(receipt.receiptRef()),receipt.candidatePhase().name(),receipt.currentPacketRevision(),receipt.currentContextFingerprint(),receipt.refreshCount(),receipt.state().name(),receipt.nextWaitEventId()==null?null:b(receipt.nextWaitEventId()),false));return 1;});
        var tx=new org.springframework.transaction.support.AbstractPlatformTransactionManager(){protected Object doGetTransaction(){return new Object();}protected void doBegin(Object t,org.springframework.transaction.TransactionDefinition d){}protected void doCommit(org.springframework.transaction.support.DefaultTransactionStatus s){}protected void doRollback(org.springframework.transaction.support.DefaultTransactionStatus s){}};
        var clock=new Clock(){public ZoneId getZone(){return ZoneOffset.UTC;}public Clock withZone(ZoneId z){return this;}public Instant instant(){return Instant.ofEpochSecond(seconds.get());}};
        service=new MemoryPacketService(true,memory,packets,mock(MemoryScopePolicy.class),mock(MemorySessionBindingService.class),mock(MemoryPolicyService.class),mock(MemoryPreferenceService.class),dependencies,mock(MemoryValueCodec.class),tx,clock,true,refresh,identity);
    }
    @Test void unknownAndPendingKeepIdenticalCandidateEvenAfterItsTtl() {
        var first=service.prepareRefreshForWait(scope,wait);seconds.addAndGet(61);
        assertEquals(first,service.prepareRefreshForWait(scope,wait));assertEquals(1,rows.size());
        service.recordReceipt(scope.tenantId(),wait.executionId(),first,new MemoryResumeReceipt(MemoryResumeReceipt.Code.MEMORY_REFRESH_PENDING,"receipt",wait.waitEventId(),first.refreshedContext().packet().packetRevision(),wait.expectedExecutionRevision(),wait.expectedPacketRevision(),wait.expectedCurrentContextFingerprint(),1L,MemoryResumeReceipt.State.REFRESH_PENDING,MemoryResumeReceipt.CandidatePhase.PENDING,null,false));
        assertEquals(first,service.prepareRefreshForWait(scope,wait));assertEquals(1,rows.size());
    }
    @Test void confirmedUnappliedExpiryAllowsSecondCandidateOnSameWait() {
        var first=service.prepareRefreshForWait(scope,wait);expire(first,1);var second=service.prepareRefreshForWait(scope,wait);
        assertNotEquals(first.resumeRequestId(),second.resumeRequestId());assertTrue(second.refreshedContext().packet().packetRevision()>first.refreshedContext().packet().packetRevision());
        assertEquals(second,service.prepareRefreshForWait(scope,wait));assertEquals(2,rows.size());assertEquals("EXPIRED_UNAPPLIED",rows.get(first.resumeRequestId()).phase());
    }
    @Test void fourthCandidateIsDeniedDespiteReplayedOldWaitCount() {
        for(int count=1;count<=3;count++)expire(service.prepareRefreshForWait(scope,wait),count);
        assertEquals("CONTEXT_REFRESH_LIMIT",assertThrows(MemoryContracts.MemoryException.class,()->service.prepareRefreshForWait(scope,wait)).code());assertEquals(3,rows.size());
    }
    @Test void appliedExpiryReplaysOldCandidateAndOnlySuccessorWaitCanRenew() {
        var first=service.prepareRefreshForWait(scope,wait);seconds.addAndGet(61);
        service.recordReceipt(scope.tenantId(),wait.executionId(),first,new MemoryResumeReceipt(MemoryResumeReceipt.Code.MEMORY_REFRESH_PACKET_EXPIRED,"applied-receipt",wait.waitEventId(),first.refreshedContext().packet().packetRevision(),wait.expectedExecutionRevision(),first.refreshedContext().packet().packetRevision(),"b".repeat(64),1L,MemoryResumeReceipt.State.WAITING_CONTEXT,MemoryResumeReceipt.CandidatePhase.APPLIED_EXPIRED,"successor-wait",false));
        assertEquals(first,service.prepareRefreshForWait(scope,wait));assertEquals(1,rows.size());
        var next=new MemoryContextWait(wait.contractVersion(),"successor-wait",wait.runtimeId(),wait.taskId(),wait.executionId(),wait.scope(),first.refreshedContext().packet().packetRevision(),wait.expectedExecutionRevision(),"b".repeat(64),wait.operationHash(),wait.logicalOperationId(),wait.semanticInputHash(),wait.canonicalRequestHmac(),wait.attempt(),wait.stageId(),wait.stageSlot(),wait.checkpointMode(),wait.checkpointNs(),wait.checkpointId(),wait.waitPhase(),wait.originalDeadline(),1);
        var successor=service.prepareRefreshForWait(scope,next);assertNotEquals(first.resumeRequestId(),successor.resumeRequestId());assertTrue(successor.refreshedContext().packet().packetRevision()>first.refreshedContext().packet().packetRevision());assertEquals(2,rows.size());
    }
    @Test void confirmedExecutionCountThreeWinsOverStaleWaitWithOneLocalCandidate() {
        var last=service.prepareRefreshForWait(scope,wait);expire(last,3);assertEquals(1,rows.size());
        assertEquals("CONTEXT_REFRESH_LIMIT",assertThrows(MemoryContracts.MemoryException.class,()->service.prepareRefreshForWait(scope,wait)).code());assertEquals(1,rows.size());
    }
    void expire(MemoryResumeRequest request,long count) {
        seconds.addAndGet(61);
        service.recordReceipt(scope.tenantId(),wait.executionId(),request,new MemoryResumeReceipt(MemoryResumeReceipt.Code.MEMORY_REFRESH_PACKET_EXPIRED,"receipt-"+count,wait.waitEventId(),request.refreshedContext().packet().packetRevision(),wait.expectedExecutionRevision(),wait.expectedPacketRevision(),wait.expectedCurrentContextFingerprint(),count,count==3?MemoryResumeReceipt.State.BLOCKED:MemoryResumeReceipt.State.WAITING_CONTEXT,MemoryResumeReceipt.CandidatePhase.EXPIRED_UNAPPLIED,null,false));
    }
    static byte[] b(String value){return MemoryMapper.identity(value);}static String text(byte[] value){return new String(value,java.nio.charset.StandardCharsets.UTF_8);}
}

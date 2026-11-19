package com.aiep.aihub.repository.memory;

import com.aiep.platformai.api.dto.MemoryResumeReceipt;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 原登录锚及只增候选；正文和凭据不进入本表。 */
@Mapper
public interface MemoryRefreshMapper {
    record Anchor(byte[] tenantId,byte[] executionId,byte[] userId,byte[] packetId,long initialPacketRevision,
        long executionRevision,String requestDigest,String semanticDigest,long originalDeadline,
        byte[] originalSessionRef,int policyTtlSeconds,long sourceRetentionDeadline) {}
    record Candidate(byte[] tenantId,byte[] executionId,byte[] resumeRequestId,byte[] waitEventId,
        long oldPacketRevision,long targetRevision,String expectedCurrentContextFingerprint,String requestHash,
        String candidateDigest,long issuedAt,long expiresAt,String phase,String receiptCode,byte[] receiptRef,
        String candidatePhase,Long currentPacketRevision,String currentContextFingerprint,Long refreshCount,
        String receiptState,byte[] nextWaitEventId,boolean dispatchAllowed) {}
    record PacketLockPO(byte[] executionId) {}
    Anchor findAnchor(@Param("tenant") byte[] tenant,@Param("execution") byte[] execution);
    PacketLockPO lockPacket(@Param("tenant") byte[] tenant,@Param("execution") byte[] execution);
    Candidate findLatestForWait(@Param("tenant") byte[] tenant,@Param("execution") byte[] execution,@Param("wait") byte[] wait);
    int countForWait(@Param("tenant") byte[] tenant,@Param("execution") byte[] execution,@Param("wait") byte[] wait);
    int maxConfirmedCount(@Param("tenant") byte[] tenant,@Param("execution") byte[] execution);
    Candidate findCandidate(@Param("tenant") byte[] tenant,@Param("execution") byte[] execution,@Param("request") byte[] request);
    Candidate findPending(@Param("tenant") byte[] tenant,@Param("execution") byte[] execution);
    Candidate findCurrent(@Param("tenant") byte[] tenant,@Param("execution") byte[] execution);
    java.util.List<Long> authorizedRevisions(@Param("tenant") byte[] tenant,@Param("execution") byte[] execution);
    long highestRevision(@Param("tenant") byte[] tenant,@Param("execution") byte[] execution);
    int insertAnchor(@Param("anchor") Anchor anchor);
    int insertCandidate(@Param("anchor") Anchor anchor,@Param("candidate") Candidate candidate);
    int complete(@Param("candidate") Candidate candidate,@Param("receipt") MemoryResumeReceipt receipt);
    int invalidCurrentInputs(@Param("tenant") byte[] tenant,@Param("user") byte[] user,@Param("domain") String domain,
        @Param("session") byte[] session,@Param("execution") byte[] execution);
}

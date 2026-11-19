package com.aiep.aihub.repository.memory;

import java.time.Instant;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 摘要本库持久端口；消息/确认事实只从本模块权威表读取，正文不得进入诊断。 */
@Mapper
public interface MemorySummaryMapper {
    record WatermarkPO(byte[] tenantId,String scopeKey,byte[] userId,String domain,String topLevelAgentId,
        byte[] sessionId,long revision,long sourceRevision,long nextSequence,long commitRevision,long coveredThrough,long deletionEpoch) {}
    record MessagePO(byte[] id,byte[] runId,String body,String contentHash,String role,boolean completed) {
        @Override public String toString(){return "SummaryMessage[redacted]";}
    }
    record AnchorPO(byte[] executionId,byte[] taskId,byte[] userId,byte[] originalSessionRef,long originalDeadline) {}
    record SourcePO(byte[] tenantId,String scopeKey,byte[] messageId,String contentHash,long sequenceNo,
        byte[] groupId,String groupMembersJson,String dependenciesJson,byte[] policyId,byte[] policyVersionId,Instant expiresAt) {}
    record BasisPO(byte[] sourceId,byte[] decisionId,byte[] itemId,byte[] versionId,byte[] actorId,String actorKind,
        String decisionType,String fieldKey,byte[] ownerId,String domain,String originTopAgentId,String lifecycle,
        byte[] currentVersionId,String versionStatus,long grantEpoch,long sourceEpoch,long deletionEpoch) {}
    record PlanPO(byte[] tenantId,String scopeKey,byte[] id,byte[] executionId,byte[] taskId,byte[] originalSessionRef,
        byte[] policyId,byte[] policyVersionId,long sessionRevision,long sourceRevision,long commitRevision,
        long originalDeadline,long expiresAt,String fingerprint,String keyVersion,byte[] encryptedPayload,byte[] nonce,
        byte[] authTag,byte[] contentHmac,String state,String transportFingerprint) {
        public PlanPO(byte[] tenantId,String scopeKey,byte[] id,byte[] executionId,byte[] taskId,byte[] originalSessionRef,
                byte[] policyId,byte[] policyVersionId,long sessionRevision,long sourceRevision,long commitRevision,
                long originalDeadline,long expiresAt,String fingerprint,String keyVersion,byte[] encryptedPayload,byte[] nonce,
                byte[] authTag,byte[] contentHmac,String state) {
            this(tenantId,scopeKey,id,executionId,taskId,originalSessionRef,policyId,policyVersionId,sessionRevision,sourceRevision,commitRevision,
                originalDeadline,expiresAt,fingerprint,keyVersion,encryptedPayload,nonce,authTag,contentHmac,state,null);
        }
        @Override public String toString(){return "SummaryPlan[redacted]";}
    }
    record SegmentPO(byte[] tenantId,String scopeKey,byte[] id,byte[] planId,long firstSequence,long lastSequence,
        long commitRevision,long expiresAt,String payloadDigest,String keyVersion,byte[] encryptedPayload,byte[] nonce,
        byte[] authTag,byte[] contentHmac,String state) {
        @Override public String toString(){return "SummarySegment[redacted]";}
    }
    int ensureWatermark(@Param("row") WatermarkPO row);
    WatermarkPO lockWatermark(@Param("tenant") byte[] tenant,@Param("scope") String scope);
    int advanceSource(@Param("row") WatermarkPO row);
    int commitWatermark(@Param("row") WatermarkPO row,@Param("last") long last,@Param("expectedCommit") long expectedCommit);
    int forgetWatermark(@Param("row") WatermarkPO row);
    MessagePO lockMessage(@Param("tenant") byte[] tenant,@Param("user") byte[] user,@Param("domain") String domain,
        @Param("session") byte[] session,@Param("message") byte[] message);
    List<MessagePO> listGroup(@Param("tenant") byte[] tenant,@Param("user") byte[] user,@Param("domain") String domain,
        @Param("session") byte[] session,@Param("run") byte[] run);
    MessagePO lockInputMessage(@Param("tenant") byte[] tenant,@Param("user") byte[] user,@Param("domain") String domain,
        @Param("session") byte[] session,@Param("source") byte[] source);
    AnchorPO findAnchor(@Param("tenant") byte[] tenant,@Param("execution") byte[] execution);
    MemoryMapper.PolicyPO lockPublishedPolicy(@Param("tenant") byte[] tenant,@Param("domain") String domain);
    SourcePO findSource(@Param("tenant") byte[] tenant,@Param("scope") String scope,@Param("message") byte[] message);
    int insertSource(@Param("row") SourcePO row);
    int insertMessageSource(@Param("tenant") byte[] tenant,@Param("message") byte[] message,
        @Param("version") byte[] version,@Param("expires") Instant expires);
    int insertSummarySource(@Param("tenant") byte[] tenant,@Param("segment") byte[] segment,@Param("version") byte[] version,@Param("expires") Instant expires);
    record SummarySourceIdPO(byte[] sourceId) {}
    List<SummarySourceIdPO> listSummarySourceIds(@Param("tenant") byte[] tenant,@Param("scope") String scope);
    int revokeSummarySource(@Param("tenant") byte[] tenant,@Param("id") byte[] id);
    BasisPO findBasis(@Param("tenant") byte[] tenant,@Param("source") byte[] source);
    PlanPO findPlan(@Param("tenant") byte[] tenant,@Param("scope") String scope,@Param("id") byte[] id);
    int insertPlan(@Param("row") PlanPO row);
    int finishPlan(@Param("tenant") byte[] tenant,@Param("scope") String scope,@Param("id") byte[] id,@Param("state") String state);
    int bindTransportFingerprint(@Param("tenant") byte[] tenant,@Param("scope") String scope,@Param("id") byte[] id,@Param("fingerprint") String fingerprint);
    int insertSegment(@Param("row") SegmentPO row);
    SegmentPO findSegment(@Param("tenant") byte[] tenant,@Param("scope") String scope,@Param("id") byte[] id);
    SegmentPO findPlanSegment(@Param("tenant") byte[] tenant,@Param("scope") String scope,@Param("plan") byte[] plan);
    List<SegmentPO> listSegments(@Param("tenant") byte[] tenant,@Param("scope") String scope);
    int scrubSegments(@Param("tenant") byte[] tenant,@Param("scope") String scope);
    int scrubPlans(@Param("tenant") byte[] tenant,@Param("scope") String scope);
    int revokeMessageSources(@Param("tenant") byte[] tenant,@Param("scope") String scope);
    int tombstoneMessageSources(@Param("tenant") byte[] tenant,@Param("scope") String scope);
}

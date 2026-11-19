package com.aiep.aihub.repository.memory;

import java.time.Instant;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 提议与source/task幂等锚持久端口；正文只保存加密封包。 */
@Mapper
public interface MemoryProposalMapper {
    record BatchPO(byte[] tenantId,byte[] taskId,byte[] executionId,byte[] userId,String domain,byte[] sessionId,
            byte[] requestId,String fingerprint,byte[] policyId,byte[] policyVersionId,String actionsJson) { }
    record ProposalPO(byte[] tenantId,byte[] id,byte[] itemId,byte[] taskId,byte[] executionId,byte[] userId,
            String domain,String topLevelAgentId,byte[] sessionId,String fieldKey,String action,String status,
            long revision,long expectedItemRevision,byte[] policyId,byte[] policyVersionId,Instant expiresAt,
            String sourceMessageIdsJson,String dependenciesJson,String keyVersion,byte[] encryptedPayload,
            byte[] nonce,byte[] authTag,byte[] contentHmac,byte[] decisionRequestId,byte[] decisionActorId,
            String decisionAction,long decisionExpectedRevision,long decisionExpectedItemRevision,byte[] acceptedVersionId) {
        @Override public String toString(){return "MemoryProposalRow[redacted]";}
    }
    BatchPO lockBatch(@Param("tenant") byte[] tenant,@Param("task") byte[] task);
    int insertBatch(@Param("row") BatchPO row);
    int claimSource(@Param("tenant") byte[] tenant,@Param("task") byte[] task,@Param("source") byte[] source,@Param("version") byte[] version);
    int ensureItem(@Param("item") MemoryMapper.MemoryItemPO item);
    int insertProposal(@Param("row") ProposalPO row);
    ProposalPO readProposal(@Param("tenant") byte[] tenant,@Param("id") byte[] id);
    ProposalPO lockProposal(@Param("tenant") byte[] tenant,@Param("id") byte[] id);
    List<ProposalPO> listBatch(@Param("tenant") byte[] tenant,@Param("task") byte[] task);
    List<ProposalPO> listOwned(@Param("tenant") byte[] tenant,@Param("user") byte[] user,@Param("domain") String domain,
            @Param("session") byte[] session,@Param("limit") int limit);
    List<byte[]> pendingValues(@Param("tenant") byte[] tenant,@Param("item") byte[] item);
    int resolve(@Param("row") ProposalPO row,@Param("status") String status,@Param("request") byte[] request,
            @Param("actor") byte[] actor,@Param("action") String action,@Param("expectedItem") long expectedItem,
            @Param("version") byte[] version);
    int invalidate(@Param("row") ProposalPO row,@Param("status") String status);
    int setBatchActions(@Param("tenant") byte[] tenant,@Param("task") byte[] task,@Param("actions") String actions);
}

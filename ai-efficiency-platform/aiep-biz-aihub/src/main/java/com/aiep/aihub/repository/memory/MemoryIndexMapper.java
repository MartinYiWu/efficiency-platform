package com.aiep.aihub.repository.memory;

import java.time.Instant;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface MemoryIndexMapper {
    Job find(@Param("tenant") byte[] tenant,@Param("id") byte[] id);
    Job requested(@Param("tenant") byte[] tenant,@Param("request") byte[] request);
    List<Job> ready(@Param("tenant") byte[] tenant,@Param("user") byte[] user,@Param("domain") String domain);
    List<Job> itemJobs(@Param("tenant") byte[] tenant,@Param("item") byte[] item);
    int insert(@Param("row") Job row);
    int transition(@Param("tenant") byte[] tenant,@Param("id") byte[] id,@Param("expected") String expected,@Param("state") String state);
    int completeOutbox(@Param("tenant") byte[] tenant,@Param("id") byte[] id);
    int indexTablePresent();
    List<Job> pendingDeletes(@Param("limit") int limit);
    List<Job> expiredReady(@Param("limit") int limit);
    int markDelete(@Param("tenant") byte[] tenant,@Param("id") byte[] id,@Param("epoch") long epoch);
    int confirmDeleted(@Param("tenant") byte[] tenant,@Param("id") byte[] id,@Param("epoch") long epoch,@Param("receipt") String receipt);
    record Job(byte[] tenantId,byte[] id,byte[] userId,String domain,byte[] itemId,byte[] versionId,
            long generation,long deletionEpoch,String sourceFingerprint,String embeddingModel,int dimension,String policyVersion,
            byte[] executionId,byte[] taskId,String executionScopeJson,Instant expiresAt,String state,
            byte[] requestId,String requestFingerprint,long deleteEpoch,String deleteReceiptRef) {
        public Job(byte[] tenantId,byte[] id,byte[] userId,String domain,byte[] itemId,byte[] versionId,long generation,long deletionEpoch,
                String sourceFingerprint,String embeddingModel,int dimension,String policyVersion,byte[] executionId,byte[] taskId,
                String executionScopeJson,Instant expiresAt,String state,byte[] requestId,String requestFingerprint) {
            this(tenantId,id,userId,domain,itemId,versionId,generation,deletionEpoch,sourceFingerprint,embeddingModel,dimension,policyVersion,
                executionId,taskId,executionScopeJson,expiresAt,state,requestId,requestFingerprint,deletionEpoch,null);
        }
    }
}

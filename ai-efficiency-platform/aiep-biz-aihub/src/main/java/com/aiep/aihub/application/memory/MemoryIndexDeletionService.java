package com.aiep.aihub.application.memory;

import com.aiep.aihub.application.memory.MemoryCleanupAckAdapter.*;
import com.aiep.aihub.application.memory.MemoryDeletionService.RevocationRequest;
import com.aiep.aihub.repository.memory.*;
import com.aiep.aihub.repository.memory.MemoryIndexMapper.Job;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.MemoryPacketDigest;
import com.aiep.platformai.api.dto.MemorySemanticTransport.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.*;

/** 索引删除只调用CPU端口；无模型/Embedding/预算授权，未知回执沿同持久命令补偿。 */
@Service
public class MemoryIndexDeletionService implements IndexDeletionPort {
    private static final ObjectMapper JSON=new ObjectMapper();
    private final MemoryIndexMapper mapper;
    private final AiInvokeFacade ai;
    private final TransactionTemplate transactions;
    public MemoryIndexDeletionService(MemoryIndexMapper mapper,AiInvokeFacade ai,PlatformTransactionManager manager){
        this.mapper=mapper;this.ai=ai;this.transactions=new TransactionTemplate(manager);
        transactions.setIsolationLevel(org.springframework.transaction.TransactionDefinition.ISOLATION_READ_COMMITTED);
    }
    @Override public IndexDeletionProof acknowledgeIndex(RevocationRequest request){
        outside();
        var jobs=transactions.execute(tx->{
            if(mapper.indexTablePresent()==0)return List.<Job>of();
            var affected=new TreeSet<String>();affected.add(request.itemId());
            for(var dep:request.dependencies())if("MEMORY_VERSION".equals(dep.targetType()))affected.add(text(dep.targetId()));
            var result=new ArrayList<Job>();
            for(String item:affected)for(var row:mapper.itemJobs(b(request.tenantId()),b(item))){
                if(!Set.of("DELETED","DELETE_PENDING").contains(row.state()))mapper.markDelete(row.tenantId(),row.id(),Math.max(row.deletionEpoch(),request.deletionEpoch()));
                result.add(mapper.find(row.tenantId(),row.id()));
            }
            return List.copyOf(result);
        });
        if(jobs.isEmpty())return new IndexDeletionProof(true,null);
        for(var job:jobs)delete(job);
        boolean complete=transactions.execute(tx->{for(var job:jobs){var row=mapper.find(job.tenantId(),job.id());if(row==null||!"DELETED".equals(row.state())||row.deleteReceiptRef()==null)return false;}return true;});
        return complete?new IndexDeletionProof(false,"memory-INDEX:"+hash(List.of(request.tenantId(),request.eventId(),request.deletionEpoch()))):new IndexDeletionProof(false,null);
    }
    /** 每批最多16个refs-only Job；关闭index读取/新写入不妨碍CPU删除历史已配置索引。 */
    @Scheduled(fixedDelayString="${aiep.memory.index-delete-scan-delay-ms:60000}")
    public void compensate(){
        outside();
        if(mapper.indexTablePresent()==0)return;
        for(var expected:mapper.expiredReady(16)){
            transactions.executeWithoutResult(tx->{
                var row=mapper.find(expected.tenantId(),expected.id());
                if(row!=null&&"READY".equals(row.state())&&row.expiresAt()!=null&&!row.expiresAt().isAfter(java.time.Instant.now()))
                    mapper.markDelete(row.tenantId(),row.id(),row.deletionEpoch());
            });
        }
        for(var job:mapper.pendingDeletes(16)){
            try{delete(job);}catch(RuntimeException unresolved){/* DELETE_PENDING持久保留，不清原费用/外发状态。 */}
        }
    }
    private void delete(Job expected){
        outside();
        var request=transactions.execute(tx->{
            var row=mapper.find(expected.tenantId(),expected.id());
            if(row==null||"DELETED".equals(row.state()))return null;
            if(!"DELETE_PENDING".equals(row.state()))throw new IllegalStateException("MEMORY_INDEX_DELETE_PENDING_REQUIRED");
            return new Delete("delete-"+hash(List.of(text(row.tenantId()),text(row.id()),row.generation(),row.deleteEpoch())),
                new Scope(text(row.tenantId()),text(row.userId()),row.domain(),row.domain(),"USER_PRIVATE",text(row.userId())),text(row.itemId()),row.generation(),row.deleteEpoch());
        });
        if(request==null)return;
        var receipt=ai.deleteMemoryIndex(request.scope().tenantId(),request);if(receipt==null)throw new IllegalStateException("MEMORY_INDEX_RECEIPT_INVALID");receipt.validate(request);
        transactions.executeWithoutResult(tx->{
            var row=mapper.find(expected.tenantId(),expected.id());
            if("DELETED".equals(row.state()))return;
            if(mapper.confirmDeleted(row.tenantId(),row.id(),request.deletionEpoch(),request.eventId())!=1)throw new IllegalStateException("MEMORY_INDEX_DELETE_CONFLICT");
            mapper.completeOutbox(row.tenantId(),row.id());
        });
    }
    private static void outside(){if(TransactionSynchronizationManager.isActualTransactionActive())throw new IllegalStateException("MEMORY_CLEANUP_OUTSIDE_TRANSACTION_REQUIRED");}
    private static String hash(Object value){return MemoryPacketDigest.canonicalDigest(JSON.valueToTree(value));}
    private static byte[] b(String value){return MemoryMapper.identity(value);}private static String text(byte[] value){return new String(value,StandardCharsets.UTF_8);}
}

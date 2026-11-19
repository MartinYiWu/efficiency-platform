package com.aiep.aihub.api.memory;

import com.aiep.platformai.api.dto.MemoryContextPacket.Dependency;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** 提议只保存待确认值；scope、来源授权和任务身份在Java重新冻结，不接受模型授予权限。 */
public final class MemoryProposalContracts {
    private MemoryProposalContracts() { }
    public enum Action { ADD, REPLACE_CANDIDATE, CONFLICT_CANDIDATE, NOOP }
    public enum Status { PENDING, ACCEPTED, REJECTED, STALE, SUPPRESSED, EXPIRED }
    public enum Decision { CONFIRM, REJECT }
    public record Candidate(String kind,String fieldKey,String value) {
        public Candidate {
            if(!"PREFERENCE".equals(kind)||fieldKey==null||!Set.of("response.language","response.detail_level","response.format").contains(fieldKey)) invalid();
            if(value==null||value.isBlank()||value.codePoints().anyMatch(cp->cp>=0xd800&&cp<=0xdfff)
                    ||value.getBytes(StandardCharsets.UTF_8).length+128>512) invalid();
        }
        @Override public String toString(){return "MemoryCandidate[redacted]";}
    }
    /** CPU用户候选与未来受控derive结果共用持久口；来源仅给消息ID，禁止自报epoch/purpose。 */
    public record Submission(MemoryScopeDTO scope,String executionId,List<String> sourceMessageIds,
            List<Candidate> candidates,String idempotencyKey) {
        public Submission {
            if(scope==null||!"CONVERSATION".equals(scope.sessionKind())||"hr".equals(scope.domain())) invalid();
            identifier(executionId);identifier(idempotencyKey);
            if(sourceMessageIds==null||sourceMessageIds.isEmpty()||sourceMessageIds.size()>128
                    ||new HashSet<>(sourceMessageIds).size()!=sourceMessageIds.size()
                    ||candidates==null||candidates.isEmpty()||candidates.size()>16) invalid();
            sourceMessageIds=List.copyOf(sourceMessageIds);sourceMessageIds.forEach(MemoryProposalContracts::identifier);
            candidates=List.copyOf(candidates).stream().distinct().toList();
        }
        @Override public String toString(){return "MemoryProposalSubmission[redacted]";}
    }
    public record DecisionCommand(MemoryScopeDTO scope,long expectedProposalRevision,long expectedItemRevision,
            Decision action,String idempotencyKey) {
        public DecisionCommand {
            if(scope==null||action==null||expectedProposalRevision<0||expectedItemRevision<0) invalid();
            identifier(idempotencyKey);
        }
    }
    public record Proposal(String id,String itemId,MemoryScopeDTO scope,String fieldKey,String value,
            Action action,Status status,long revision,long expectedItemRevision,Instant expiresAt,
            String indexStatus,String versionId,List<Dependency> sourceDependencies) {
        public Proposal {sourceDependencies=List.copyOf(sourceDependencies);}
        @Override public String toString(){return "MemoryProposal[redacted]";}
    }
    public record BatchResult(String taskId,List<Proposal> proposals,List<Action> actions) {
        public BatchResult {proposals=List.copyOf(proposals);actions=List.copyOf(actions);}
        @Override public String toString(){return "MemoryProposalBatch[redacted]";}
    }
    public static void identifier(String value) {
        if(value==null||value.isBlank()||value.codePointCount(0,value.length())>128
                ||value.getBytes(StandardCharsets.UTF_8).length>512||value.codePoints().anyMatch(cp->cp>=0xd800&&cp<=0xdfff)) invalid();
    }
    private static void invalid(){throw new MemoryContracts.MemoryException("MEMORY_PROPOSAL_INVALID");}
}

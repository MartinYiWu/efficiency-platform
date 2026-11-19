package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.MemoryProposalContracts.Action;
import java.security.MessageDigest;
import java.util.List;
import org.springframework.stereotype.Service;

/** 等值去重先行；有矛盾保持原ACTIVE，只有后续有权确认才能替换。 */
@Service
public class MemoryConflictService {
    public Action classify(byte[] proposed,byte[] current,List<byte[]> pending) {
        if(pending.stream().anyMatch(value->!MessageDigest.isEqual(proposed,value))) return Action.CONFLICT_CANDIDATE;
        if(current!=null&&!MessageDigest.isEqual(proposed,current)) return Action.CONFLICT_CANDIDATE;
        if(current!=null||!pending.isEmpty()) return Action.NOOP;
        return Action.ADD;
    }
}

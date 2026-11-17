package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/** Java已鉴权且完整血缘的有界历史组；HTTP正文摘要覆盖全部字段。 */
public record MemoryHistoryMessage(@JsonProperty("message_id") String messageId,String version,String role,String content,
        @JsonProperty("safety_dependencies") List<MemoryContextPacket.Dependency> safetyDependencies) {
    public MemoryHistoryMessage {
        MemoryContextPacket.requireId(messageId);MemoryContextPacket.requireId(version);
        if(!List.of("user","assistant").contains(role)||content==null||content.isBlank()||content.length()>12000)
            throw new IllegalArgumentException("MEMORY_HISTORY_INVALID");
        safetyDependencies=List.copyOf(safetyDependencies);
        if(safetyDependencies.isEmpty())throw new IllegalArgumentException("MEMORY_HISTORY_LINEAGE_REQUIRED");
    }
    @Override public String toString(){return "MemoryHistoryMessage[redacted]";}
}

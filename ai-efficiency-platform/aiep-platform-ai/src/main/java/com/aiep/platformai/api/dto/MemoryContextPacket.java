package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/** 中立完整传输包；认证来自内部通道，摘要本身不授予权限。 */
public record MemoryContextPacket(
        @JsonProperty("packet_id") String packetId,
        @JsonProperty("packet_revision") long packetRevision,
        MemoryContextEnvelope.Scope scope,
        @JsonProperty("task_id") String taskId,
        @JsonProperty("execution_id") String executionId,
        @JsonProperty("policy_version") String policyVersion,
        @JsonProperty("execution_revision") long executionRevision,
        @JsonProperty("issued_at") long issuedAt,
        @JsonProperty("expires_at") long expiresAt,
        @JsonProperty("grant_epoch") long grantEpoch,
        @JsonProperty("source_epoch") long sourceEpoch,
        @JsonProperty("deletion_epoch") long deletionEpoch,
        @JsonProperty("semantic_input_hash") String semanticInputHash,
        @JsonProperty("parent_authorization_ref") String parentAuthorizationRef,
        List<Item> items,
        @JsonProperty("safety_dependencies") List<Dependency> safetyDependencies) {
    public MemoryContextPacket {
        for (String id : List.of(packetId, taskId, executionId, policyVersion, semanticInputHash, parentAuthorizationRef))
            requireId(id);
        if (scope == null || packetRevision < 0 || executionRevision < 0 || issuedAt < 0
                || expiresAt <= issuedAt || grantEpoch < 0 || sourceEpoch < 0 || deletionEpoch < 0)
            throw new IllegalArgumentException("MEMORY_PACKET_INVALID");
        items = List.copyOf(items);
        safetyDependencies = List.copyOf(safetyDependencies);
        for (var item : items)
            if (!safetyDependencies.containsAll(item.safetyDependencies()))
                throw new IllegalArgumentException("MEMORY_DEPENDENCIES_INVALID");
    }

    static void requireId(String id) {
        if (id == null || id.isBlank() || id.codePointCount(0, id.length()) > 128
                || id.codePoints().anyMatch(cp -> cp >= 0xd800 && cp <= 0xdfff))
            throw new IllegalArgumentException("MEMORY_IDENTIFIER_INVALID");
    }

    public record Item(@JsonProperty("item_id") String itemId, String version,
            @JsonProperty("field_key") String fieldKey, String value,
            @JsonProperty("safety_dependencies") List<Dependency> safetyDependencies) {
        public Item {
            requireId(itemId); requireId(version); requireId(fieldKey);
            if (value == null) throw new IllegalArgumentException("MEMORY_VALUE_INVALID");
            safetyDependencies = List.copyOf(safetyDependencies);
        }
        @Override public String toString() { return "MemoryPacketItem[redacted]"; }
    }

    public record Dependency(@JsonProperty("source_type") String sourceType,
            @JsonProperty("source_id") String sourceId,
            @JsonProperty("source_version") String sourceVersion,
            @JsonProperty("grant_epoch") long grantEpoch,
            @JsonProperty("source_epoch") long sourceEpoch,
            @JsonProperty("deletion_epoch") long deletionEpoch) {
        public Dependency {
            requireId(sourceType); requireId(sourceId); requireId(sourceVersion);
            if (grantEpoch < 0 || sourceEpoch < 0 || deletionEpoch < 0)
                throw new IllegalArgumentException("MEMORY_EPOCH_INVALID");
        }
    }
}

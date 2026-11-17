package com.aiep.aihub.domain.memory;

import com.aiep.aihub.api.memory.MemoryScopeDTO;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Set;

/** 私有偏好逻辑键以用户和来源顶层Agent隔离，session不进入偏好键。 */
public record MemoryKey(String tenantId, String subjectId, String domain, String fieldKey) {
    public static final Set<String> PREFERENCE_FIELDS = Set.of("response.language", "response.detail_level", "response.format");

    public MemoryKey {
        if (!PREFERENCE_FIELDS.contains(fieldKey)) throw new IllegalArgumentException("MEMORY_FIELD_INVALID");
        for (String id : new String[] {tenantId, subjectId}) {
            if (id == null || id.isBlank() || id.codePointCount(0, id.length()) > 128
                    || id.codePoints().anyMatch(cp -> cp >= 0xd800 && cp <= 0xdfff)
                    || id.getBytes(StandardCharsets.UTF_8).length > 512)
                throw new IllegalArgumentException("MEMORY_IDENTITY_INVALID");
        }
        if (!Set.of("operations", "customer-service", "hr").contains(domain))
            throw new IllegalArgumentException("MEMORY_ORIGIN_AGENT_INVALID");
    }

    public static MemoryKey preference(MemoryScopeDTO scope, String fieldKey) {
        return new MemoryKey(scope.tenantId(), scope.userId(), scope.topLevelAgentId(), fieldKey);
    }

    public String subjectType() { return "USER"; }
    public String scopeType() { return "USER_PRIVATE"; }
    public String purpose() { return "assistant_response"; }

    /** 与D10的up1编码逐字节一致；长度前缀不丢失尾空格或128个补充平面字符。 */
    public byte[] scopeId() {
        byte[] user = subjectId.getBytes(StandardCharsets.UTF_8);
        byte[] agent = domain.getBytes(StandardCharsets.US_ASCII);
        return ByteBuffer.allocate(8 + user.length + agent.length).put("up1:".getBytes(StandardCharsets.US_ASCII))
                .putInt(user.length).put(user).put(agent).array();
    }
}

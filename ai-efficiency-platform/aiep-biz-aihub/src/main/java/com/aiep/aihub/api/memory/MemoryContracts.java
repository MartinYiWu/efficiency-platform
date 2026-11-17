package com.aiep.aihub.api.memory;

import java.util.List;

/** 私有记忆服务合同；不接受调用方自报owner、授权字段或会话凭据。 */
public final class MemoryContracts {
    private MemoryContracts() { }

    /** 确定性单字段命令；revision与幂等键供后续写事务使用，null抑制代次不表示重新授权。 */
    public record PreferenceCommand(MemoryScopeDTO scope, String fieldKey, String value,
            long expectedRevision, String idempotencyKey, Long expectedSuppressionRevision) { }

    /** 首期遗忘语义固定为忘记并抑制；未开放的删除模式不接受客户端扩展。 */
    public record ForgetCommand(MemoryScopeDTO scope, long expectedRevision, String idempotencyKey) { }

    /** 来源已由业务服务鉴权的任务执行；TASK_ONLY不以null session建立历史桶。 */
    public record Execution(MemoryScopeDTO scope, String taskId, String executionId) { }

    /** 已确认偏好的API投影，不暴露持久化对象或会话引用。 */
    public record Preference(String id, String versionId, MemoryScopeDTO scope, String fieldKey,
            String value, long revision, String status, String sourceType, String sourceRef, java.time.Instant expiresAt) {
        public Preference(String id,String versionId,MemoryScopeDTO scope,String fieldKey,String value,long revision) {
            this(id,versionId,scope,fieldKey,value,revision,null,null,null,null);
        }
    }
    public record PreferenceHistory(Preference preference,List<Preference> history) {
        public PreferenceHistory { history=List.copyOf(history); }
    }

    /** 后续包组装的服务结果；本阶段尚未开放签发。 */
    public record Packet(String packetId, long revision, MemoryScopeDTO scope, List<Preference> preferences) {
        public Packet { preferences = List.copyOf(preferences); }
    }

    /** 稳定业务错误只携带安全错误码，不回显身份、正文或凭据。 */
    public static final class MemoryException extends RuntimeException {
        private final String code;
        public MemoryException(String code) { super(code); this.code = code; }
        public String code() { return code; }
    }
}

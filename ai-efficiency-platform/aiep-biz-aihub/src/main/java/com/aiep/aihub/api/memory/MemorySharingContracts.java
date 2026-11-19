package com.aiep.aihub.api.memory;

import java.time.Instant;
import java.util.List;
import java.util.Set;

/** 显式白名单共享；memory scope不授予任何源业务对象权限。 */
public final class MemorySharingContracts {
    private MemorySharingContracts() { }
    public static final Set<String> FIELDS=Set.of("response.language","response.detail_level","response.format");
    public static final Set<String> AGENTS=Set.of("operations","customer-service");
    public record GrantCommand(String originAgent,String itemId,String versionId,String targetAgent,
            long expectedItemRevision,Instant expiresAt,String idempotencyKey) { }
    public record ScopeCommand(String scopeType,String departmentId,String approverUserId,Instant expiresAt,String idempotencyKey) { }
    public record ShareCommand(String originAgent,String itemId,String versionId,long expectedItemRevision,
            List<String> allowedAgents,Instant expiresAt,String idempotencyKey) {
        public ShareCommand {allowedAgents=List.copyOf(allowedAgents);}
    }
    public record RevisionCommand(long expectedRevision,String idempotencyKey) { }
    public record MemberCommand(String userId,long expectedRevision,String idempotencyKey) { }
    public record MembershipCommand(long expectedRevision,String action,String idempotencyKey) { }
    public record GrantView(String id,String itemId,String versionId,String fieldKey,String originAgent,
            String targetAgent,long revision,String status,@com.fasterxml.jackson.annotation.JsonFormat(shape=com.fasterxml.jackson.annotation.JsonFormat.Shape.STRING) Instant expiresAt,String indexStatus) { }
    public record ScopeView(String id,String scopeType,String departmentId,String ownerUserId,String approverUserId,
            long revision,String status,String membershipStatus,long membershipRevision,@com.fasterxml.jackson.annotation.JsonFormat(shape=com.fasterxml.jackson.annotation.JsonFormat.Shape.STRING) Instant expiresAt) { }
    public record ShareView(String id,String scopeId,String itemId,String versionId,String fieldKey,String originAgent,
            List<String> allowedAgents,String ownerUserId,long revision,String status,@com.fasterxml.jackson.annotation.JsonFormat(shape=com.fasterxml.jackson.annotation.JsonFormat.Shape.STRING) Instant expiresAt,String indexStatus) {
        public ShareView {allowedAgents=List.copyOf(allowedAgents);}
    }
}

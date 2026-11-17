package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.domain.memory.MemoryKey;
import com.aiep.identity.api.IdentityFacade;
import java.util.Objects;
import java.util.Set;
import org.springframework.stereotype.Component;

/** 本人私有偏好与HR业务正文是不同授权；配置管理权不能授予正文访问。 */
@Component
public class MemoryScopePolicy {
    private static final Set<String> HR_SOURCE_PERMISSIONS = Set.of("hr:candidate:read", "hr:candidate:original", "hr:position:read");
    private final IdentityFacade identity;
    private final MemoryActorProvider actors;

    public MemoryScopePolicy(IdentityFacade identity, MemoryActorProvider actors) {
        this.identity = identity;
        this.actors = actors;
    }

    /** HTTP层从真实provider捕获主体；异步阶段仍使用捕获的原sessionRef。 */
    public IdentityFacade.Subject currentActor() {
        var actor = actors.current();
        return refresh(actor.tenantId(), actor.userId(), actor.sessionRef());
    }

    public void require(IdentityFacade.Subject actor, MemoryScopeDTO scope, Set<String> fieldKeys) {
        var current = refresh(actor.tenantId(), actor.userId(), actor.sessionRef());
        if (scope == null || !current.tenantId().equals(scope.tenantId()) || !current.userId().equals(scope.userId()))
            throw new MemoryException("MEMORY_SCOPE_DENIED");
        if (fieldKeys == null || !MemoryKey.PREFERENCE_FIELDS.containsAll(fieldKeys))
            throw new MemoryException("FEATURE_DISABLED");
    }

    /** HR源读取要求同条当前授权tuple；权限、部门和对象不得分别取并集。 */
    public void requireHrSource(IdentityFacade.Subject actor, String permission, String department, String position, String candidate) {
        var current = refresh(actor.tenantId(), actor.userId(), actor.sessionRef());
        boolean granted = HR_SOURCE_PERMISSIONS.contains(permission) && current.permissions().contains(permission)
                && department != null && current.departmentIds().contains(department)
                && (position != null || candidate != null)
                && current.grants().stream().anyMatch(grant -> permission.equals(grant.permission())
                    && Objects.equals(department, grant.departmentId())
                    && Objects.equals(position, grant.positionId()) && Objects.equals(candidate, grant.candidateId()));
        if (!granted) throw new MemoryException("MEMORY_SCOPE_DENIED");
    }

    /** 只比较已经由服务器鉴权的范围，不对任意客户端scope授予读取许可。 */
    public boolean canReadHistory(MemoryScopeDTO authorized, MemoryScopeDTO source) {
        return authorized != null && source != null && authorized.historyKey() != null
                && authorized.historyKey().equals(source.historyKey());
    }

    private IdentityFacade.Subject refresh(String tenant, String user, String sessionRef) {
        if (sessionRef == null || sessionRef.isBlank()) throw new MemoryException("MEMORY_IDENTITY_REQUIRED");
        var current = identity.refresh(tenant, user, sessionRef)
                .orElseThrow(() -> new MemoryException("MEMORY_IDENTITY_REQUIRED"));
        if (!tenant.equals(current.tenantId()) || !user.equals(current.userId()) || !sessionRef.equals(current.sessionRef()))
            throw new MemoryException("MEMORY_IDENTITY_REQUIRED");
        return current;
    }
}

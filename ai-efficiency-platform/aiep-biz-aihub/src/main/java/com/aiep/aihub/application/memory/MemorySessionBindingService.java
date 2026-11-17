package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.application.operation.OperationActor;
import com.aiep.aihub.repository.memory.MemoryMapper;
import com.aiep.aihub.repository.memory.MemoryMapper.SessionBindingPO;
import com.aiep.identity.api.IdentityFacade;
import java.util.Arrays;
import java.util.Set;
import java.util.UUID;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 绑定只是元数据；每次重新查真实业务会话拥有关系，不能作为新的正文授权来源。 */
@Service
public class MemorySessionBindingService {
    private final MemoryMapper mapper;
    private final MemoryScopePolicy policy;
    private final ConversationScopeResolver scopes;

    public MemorySessionBindingService(MemoryMapper mapper, MemoryScopePolicy policy, ConversationScopeResolver scopes) {
        this.mapper = mapper;
        this.policy = policy;
        this.scopes = scopes;
    }

    /** 初次写入唯一，竞争只读取赢家，永不更新原归属；旧会话同样从固定业务表回填。 */
    @Transactional
    public MemoryScopeDTO bind(IdentityFacade.Subject actor, String topAgent, String sessionId) {
        if (!Set.of("operations", "customer-service").contains(topAgent)) throw new MemoryException("MEMORY_SCOPE_DENIED");
        var scope = new MemoryScopeDTO(actor.tenantId(), actor.userId(), topAgent, topAgent, "CONVERSATION", sessionId);
        policy.require(actor, scope, Set.of());
        byte[] tenant = MemoryMapper.identity(scope.tenantId()), user = MemoryMapper.identity(scope.userId()), session = MemoryMapper.identity(sessionId);
        var owner = "operations".equals(topAgent) ? mapper.findOperationOwner(tenant, user, session)
                : mapper.findCustomerServiceOwner(tenant, user, session);
        if (owner == null || !Arrays.equals(tenant, owner.tenantId()) || !Arrays.equals(user, owner.userId()) || !Arrays.equals(session, owner.sessionId()))
            throw new MemoryException("MEMORY_SCOPE_DENIED");
        String type = "operations".equals(topAgent) ? "OPERATION_CONVERSATION" : "CUSTOMER_SERVICE_CONVERSATION";
        SessionBindingPO existing = mapper.findSessionBinding(tenant, user, session);
        if (existing != null) return requireBinding(existing, scope, type);
        var binding = new SessionBindingPO(tenant, MemoryMapper.identity(UUID.randomUUID().toString()), user, topAgent,
                topAgent, session, "CONVERSATION", type, session);
        try {
            if (mapper.insertSessionBinding(binding) != 1) throw new MemoryException("MEMORY_SESSION_BINDING_CONFLICT");
        } catch (DuplicateKeyException conflict) {
            return requireBinding(mapper.findSessionBinding(tenant, user, session), scope, type);
        }
        return scopes.conversation(new OperationActor(scope.tenantId(), scope.userId(), actor.sessionRef()), topAgent,
                sessionId, scope.tenantId(), scope.userId(), topAgent);
    }

    /** 后续Facade在使用scope前调用；HR仅校验本人TASK_ONLY，不查询或建立会话桶。 */
    @Transactional
    public void require(IdentityFacade.Subject actor, MemoryScopeDTO scope) {
        policy.require(actor, scope, Set.of());
        if ("CONVERSATION".equals(scope.sessionKind())) bind(actor, scope.topLevelAgentId(), scope.sessionId());
    }

    private MemoryScopeDTO requireBinding(SessionBindingPO binding, MemoryScopeDTO scope, String type) {
        if (binding == null || !Arrays.equals(binding.tenantId(), MemoryMapper.identity(scope.tenantId()))
                || !Arrays.equals(binding.userId(), MemoryMapper.identity(scope.userId()))
                || !Arrays.equals(binding.sessionId(), MemoryMapper.identity(scope.sessionId()))
                || !scope.domain().equals(binding.domain()) || !scope.topLevelAgentId().equals(binding.topLevelAgentId())
                || !"CONVERSATION".equals(binding.sessionKind()) || !type.equals(binding.originalObjectType())
                || !Arrays.equals(binding.originalObjectId(), MemoryMapper.identity(scope.sessionId())))
            throw new MemoryException("MEMORY_SESSION_BINDING_CONFLICT");
        return scope;
    }
}

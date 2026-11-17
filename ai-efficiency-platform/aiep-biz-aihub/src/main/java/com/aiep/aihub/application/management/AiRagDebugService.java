package com.aiep.aihub.application.management;

import com.aiep.aihub.repository.management.AiManagementMappers;
import com.aiep.aihub.repository.management.AiReleasePO;
import com.aiep.aihub.application.memory.MemoryActorProvider;
import com.aiep.aihub.application.memory.ConversationScopeResolver;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.CustomerServiceDebugRequest;
import com.aiep.platformai.api.dto.CustomerServiceDebugView;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class AiRagDebugService {
    private final AiManagementMappers repository;
    private final AiInvokeFacade ai;
    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;
    private final MemoryActorProvider actors;
    private final ConversationScopeResolver scopes = new ConversationScopeResolver();

    public AiRagDebugService(AiManagementMappers repository, AiInvokeFacade ai, JdbcTemplate jdbc, ObjectMapper objectMapper) {
        this(repository, ai, jdbc, objectMapper, new MemoryActorProvider() {
            public com.aiep.aihub.application.operation.OperationActor current() { throw new IllegalStateException("MEMORY_IDENTITY_REQUIRED"); }
            public com.aiep.aihub.application.operation.OperationActor revalidate(com.aiep.aihub.application.operation.OperationActor actor) { throw new IllegalStateException("MEMORY_IDENTITY_REQUIRED"); }
        });
    }

    @org.springframework.beans.factory.annotation.Autowired
    public AiRagDebugService(AiManagementMappers repository, AiInvokeFacade ai, JdbcTemplate jdbc,
            ObjectMapper objectMapper, MemoryActorProvider actors) {
        this.repository = repository; this.ai = ai; this.jdbc = jdbc; this.objectMapper = objectMapper; this.actors = actors;
    }

    public CustomerServiceDebugView execute(Request request) {
        var actor = actors.current();
        var agent = repository.findAgentByKey(request.agentKey());
        var version = repository.findAgentVersion(request.agentVersionId());
        var rag = repository.findRagPolicy(request.ragPolicyVersionId());
        if (agent == null || version == null || !agent.id().equals(version.agentDefinitionId())
                || rag == null || !agent.id().equals(rag.ownerAgentDefinitionId()))
            throw new AiManagementException("AI_ASSET_OWNER_MISMATCH", "调试 Agent、版本或 RAG 策略不存在或归属不匹配");
        AiReleasePO release = repository.findActiveRelease(agent.id(), "dev");
        var policyBinding = repository.findPolicyBinding(version.id());
        if (release == null || !release.agentVersionId().equals(version.id())
                || policyBinding == null || !request.ragPolicyVersionId().equals(policyBinding.ragPolicyId()))
            throw new AiManagementException("AI_RAG_DEBUG_ACTIVE_RELEASE_MISMATCH", "调试 Agent 版本或 RAG 策略与当前生效发布不匹配");
        if (request.knowledgeBindings() == null || request.knowledgeBindings().isEmpty()
                || request.knowledgeBindings().stream().anyMatch(item -> !repository.isIndexReleaseReady(item.indexReleaseId())))
            throw new AiManagementException("AI_RAG_DEBUG_INDEX_NOT_READY", "调试知识索引未就绪，请选择已发布且可用的索引");
        CustomerServiceDebugRequest agentRequest = new CustomerServiceDebugRequest(
                "customer-service-rag-debug/1", request.agentKey(), actor.tenantId(), request.question(), release.id(), request.agentVersionId(),
                request.ragPolicyVersionId(), request.knowledgeBindings().stream()
                        .map(item -> new CustomerServiceDebugRequest.KnowledgeBinding(item.knowledgeBaseId(), item.indexReleaseId())).toList(),
                scopes.envelope(scopes.taskOnly(actor, "customer-service")));
        CustomerServiceDebugView response = ai.debugCustomerServiceRag(agentRequest);
        actors.revalidate(actor);
        jdbc.update("INSERT INTO ai_rag_debug_run (id,agent_key,agent_version_id,rag_policy_version_id,question,request_json,response_json,status,created_by,created_at) "
                        + "VALUES (?,?,?,?,?,CAST(? AS JSON),CAST(? AS JSON),?,?,NOW(6))",
                response.debugRunId(), request.agentKey(), request.agentVersionId(), request.ragPolicyVersionId(), request.question(),
                json(agentRequest), json(response), response.status(), actor.userId());
        return response;
    }

    public CustomerServiceDebugView get(String id) {
        var actor = actors.current();
        String value = jdbc.query("SELECT response_json FROM ai_rag_debug_run WHERE id=? "
                + "AND CAST(JSON_UNQUOTE(JSON_EXTRACT(request_json,'$.memory_context.scope.tenant_id')) AS BINARY)=CAST(? AS BINARY) "
                + "AND CAST(JSON_UNQUOTE(JSON_EXTRACT(request_json,'$.memory_context.scope.user_id')) AS BINARY)=CAST(? AS BINARY)",
                rs -> rs.next() ? rs.getString(1) : null, id, actor.tenantId(), actor.userId());
        if (value == null) throw new AiManagementException("AI_RAG_DEBUG_RUN_NOT_FOUND", "RAG 调试记录不存在");
        try { return objectMapper.readValue(value, CustomerServiceDebugView.class); }
        catch (JsonProcessingException error) { throw new IllegalStateException("AI_RAG_DEBUG_RESULT_INVALID", error); }
    }

    private String json(Object value) {
        try { return objectMapper.writeValueAsString(value); }
        catch (JsonProcessingException error) { throw new IllegalArgumentException("AI_RAG_DEBUG_REQUEST_INVALID", error); }
    }

    public record Request(String agentKey, String question, String agentVersionId, String ragPolicyVersionId,
                          List<KnowledgeBinding> knowledgeBindings) { }
    public record KnowledgeBinding(String knowledgeBaseId, String indexReleaseId) { }
}

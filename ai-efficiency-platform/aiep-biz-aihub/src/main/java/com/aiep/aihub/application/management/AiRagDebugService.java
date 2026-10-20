package com.aiep.aihub.application.management;

import com.aiep.aihub.repository.management.AiManagementMappers;
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

    public AiRagDebugService(AiManagementMappers repository, AiInvokeFacade ai, JdbcTemplate jdbc, ObjectMapper objectMapper) {
        this.repository = repository; this.ai = ai; this.jdbc = jdbc; this.objectMapper = objectMapper;
    }

    public CustomerServiceDebugView execute(Request request) {
        var agent = repository.findAgentByKey(request.agentKey());
        var version = repository.findAgentVersion(request.agentVersionId());
        var rag = repository.findRagPolicy(request.ragPolicyVersionId());
        if (agent == null || version == null || !agent.id().equals(version.agentDefinitionId())
                || rag == null || !agent.id().equals(rag.ownerAgentDefinitionId()))
            throw new IllegalArgumentException("AI_ASSET_OWNER_MISMATCH");
        if (request.knowledgeBindings() == null || request.knowledgeBindings().isEmpty()
                || request.knowledgeBindings().stream().anyMatch(item -> !repository.isIndexReleaseReady(item.indexReleaseId())))
            throw new IllegalArgumentException("AI_RAG_DEBUG_INDEX_NOT_READY");
        CustomerServiceDebugRequest agentRequest = new CustomerServiceDebugRequest(
                "customer-service-rag-debug/1", request.agentKey(), request.question(), request.agentVersionId(),
                request.ragPolicyVersionId(), request.knowledgeBindings().stream()
                        .map(item -> new CustomerServiceDebugRequest.KnowledgeBinding(item.knowledgeBaseId(), item.indexReleaseId())).toList());
        CustomerServiceDebugView response = ai.debugCustomerServiceRag(agentRequest);
        jdbc.update("INSERT INTO ai_rag_debug_run (id,agent_key,agent_version_id,rag_policy_version_id,question,request_json,response_json,status,created_by,created_at) "
                        + "VALUES (?,?,?,?,?,CAST(? AS JSON),CAST(? AS JSON),?,'1',NOW(6))",
                response.debugRunId(), request.agentKey(), request.agentVersionId(), request.ragPolicyVersionId(), request.question(),
                json(agentRequest), json(response), response.status());
        return response;
    }

    public CustomerServiceDebugView get(String id) {
        String value = jdbc.query("SELECT response_json FROM ai_rag_debug_run WHERE id=?", rs -> rs.next() ? rs.getString(1) : null, id);
        if (value == null) throw new IllegalArgumentException("AI_RAG_DEBUG_RUN_NOT_FOUND");
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

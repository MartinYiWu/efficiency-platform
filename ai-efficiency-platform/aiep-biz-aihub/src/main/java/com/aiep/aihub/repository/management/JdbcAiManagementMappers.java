package com.aiep.aihub.repository.management;

import com.aiep.aihub.repository.management.AiManagementPOs.AgentDefinitionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionKnowledgeBindingPO;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionPolicyBindingPO;
import com.aiep.aihub.repository.management.AiManagementPOs.ModelPolicyPO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptBindingPO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptDefinitionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptMessageTemplatePO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptVariablePO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptVersionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.RagPolicyPO;
import java.util.ArrayList;
import java.util.List;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.DataClassRowMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class JdbcAiManagementMappers implements AiManagementMappers {
    private static final DataClassRowMapper<AgentDefinitionPO> AGENT = DataClassRowMapper.newInstance(AgentDefinitionPO.class);
    private static final DataClassRowMapper<AgentVersionPO> AGENT_VERSION = DataClassRowMapper.newInstance(AgentVersionPO.class);
    private static final DataClassRowMapper<PromptDefinitionPO> PROMPT = DataClassRowMapper.newInstance(PromptDefinitionPO.class);
    private static final DataClassRowMapper<PromptVersionPO> PROMPT_VERSION = DataClassRowMapper.newInstance(PromptVersionPO.class);
    private static final DataClassRowMapper<PromptMessageTemplatePO> MESSAGE = DataClassRowMapper.newInstance(PromptMessageTemplatePO.class);
    private static final DataClassRowMapper<PromptVariablePO> VARIABLE = DataClassRowMapper.newInstance(PromptVariablePO.class);
    private static final DataClassRowMapper<ModelPolicyPO> MODEL = DataClassRowMapper.newInstance(ModelPolicyPO.class);
    private static final DataClassRowMapper<RagPolicyPO> RAG = DataClassRowMapper.newInstance(RagPolicyPO.class);
    private static final DataClassRowMapper<PromptBindingPO> PROMPT_BINDING = DataClassRowMapper.newInstance(PromptBindingPO.class);
    private static final DataClassRowMapper<AgentVersionPolicyBindingPO> POLICY_BINDING = DataClassRowMapper.newInstance(AgentVersionPolicyBindingPO.class);
    private static final DataClassRowMapper<AgentVersionKnowledgeBindingPO> KNOWLEDGE_BINDING = DataClassRowMapper.newInstance(AgentVersionKnowledgeBindingPO.class);
    private static final DataClassRowMapper<AiReleasePO> RELEASE = DataClassRowMapper.newInstance(AiReleasePO.class);
    private static final DataClassRowMapper<AiReleaseSnapshotPO> RELEASE_SNAPSHOT = DataClassRowMapper.newInstance(AiReleaseSnapshotPO.class);
    private final JdbcTemplate jdbc;

    public JdbcAiManagementMappers(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public List<AgentEvidenceBindingPO> listEvidenceBindings(String agentId) {
        return jdbc.query("""
                SELECT 'VERSION' AS source_type,v.id AS source_id,m.model_name AS large_model_name,
                       m.max_input_tokens,k.knowledge_base_id,k.index_release_id AS bound_index_release_id,
                       b.current_index_release_id
                FROM ai_agent_version v
                LEFT JOIN ai_agent_version_policy_binding p ON p.agent_version_id=v.id
                LEFT JOIN ai_model_policy m ON m.id=p.large_context_model_policy_id
                LEFT JOIN ai_agent_version_knowledge_binding k ON k.agent_version_id=v.id
                LEFT JOIN kb_knowledge_base b ON b.id=k.knowledge_base_id
                WHERE v.agent_definition_id=?
                UNION ALL
                SELECT 'RELEASE',r.id,
                       NULLIF(JSON_UNQUOTE(JSON_EXTRACT(s.snapshot_json,'$.large_context_model_policy.model_name')),'null'),
                       CAST(JSON_UNQUOTE(JSON_EXTRACT(s.snapshot_json,'$.large_context_model_policy.max_input_tokens')) AS UNSIGNED),
                       k.knowledge_base_id,k.index_release_id,b.current_index_release_id
                FROM ai_agent_release r
                JOIN ai_agent_release_snapshot s ON s.id=r.release_snapshot_id
                LEFT JOIN JSON_TABLE(s.snapshot_json,'$.knowledge_bindings[*]' COLUMNS(
                    knowledge_base_id VARCHAR(64) PATH '$.knowledge_base_id',
                    index_release_id VARCHAR(64) PATH '$.index_release_id')) k ON TRUE
                LEFT JOIN kb_knowledge_base b ON b.id=k.knowledge_base_id
                WHERE r.agent_definition_id=?
                """, DataClassRowMapper.newInstance(AgentEvidenceBindingPO.class), agentId, agentId);
    }

    @Override public List<AgentDefinitionPO> listAgents() {
        return jdbc.query("SELECT * FROM ai_agent_definition ORDER BY updated_at DESC", AGENT);
    }
    @Override public AgentDefinitionPO findAgent(String id) { return one("SELECT * FROM ai_agent_definition WHERE id=?", AGENT, id); }
    @Override public AgentDefinitionPO findAgentByKey(String agentKey) { return one("SELECT * FROM ai_agent_definition WHERE agent_key=?", AGENT, agentKey); }
    @Override public void insertAgent(AgentDefinitionPO v) {
        jdbc.update("INSERT INTO ai_agent_definition (id,agent_key,name,description,agent_type,status,created_by,created_at,updated_by,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                v.id(), v.agentKey(), v.name(), v.description(), v.agentType(), v.status(), v.createdBy(), v.createdAt(), v.updatedBy(), v.updatedAt());
    }
    @Override public List<AgentVersionPO> listAgentVersions(String agentId) {
        return jdbc.query("SELECT * FROM ai_agent_version WHERE agent_definition_id=? ORDER BY created_at DESC", AGENT_VERSION, agentId);
    }
    @Override public AgentVersionPO findAgentVersion(String id) { return one("SELECT * FROM ai_agent_version WHERE id=?", AGENT_VERSION, id); }
    @Override public void insertAgentVersion(AgentVersionPO v) {
        jdbc.update("INSERT INTO ai_agent_version (id,agent_definition_id,semantic_version,graph_key,graph_version,status,change_summary,created_by,created_at,published_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                v.id(), v.agentDefinitionId(), v.semanticVersion(), v.graphKey(), v.graphVersion(), v.status(), v.changeSummary(), v.createdBy(), v.createdAt(), v.publishedAt());
    }
    @Override public void updateAgentVersion(AgentVersionPO v) {
        jdbc.update("UPDATE ai_agent_version SET semantic_version=?,graph_key=?,graph_version=?,status=?,change_summary=?,published_at=? WHERE id=?",
                v.semanticVersion(), v.graphKey(), v.graphVersion(), v.status(), v.changeSummary(), v.publishedAt(), v.id());
    }

    @Override public List<PromptDefinitionPO> listPrompts(String scope, String ownerAgentId) {
        StringBuilder sql = new StringBuilder("SELECT * FROM ai_prompt_definition WHERE 1=1");
        List<Object> args = new ArrayList<>();
        if (scope != null && !scope.isBlank()) { sql.append(" AND scope=?"); args.add(scope.toUpperCase()); }
        if (ownerAgentId != null && !ownerAgentId.isBlank()) {
            sql.append(" AND (scope='SHARED' OR owner_agent_definition_id=?)"); args.add(ownerAgentId);
        }
        sql.append(" ORDER BY prompt_key");
        return jdbc.query(sql.toString(), PROMPT, args.toArray());
    }
    @Override public PromptDefinitionPO findPromptDefinition(String id) { return one("SELECT * FROM ai_prompt_definition WHERE id=?", PROMPT, id); }
    @Override public void insertPromptDefinition(PromptDefinitionPO v) {
        jdbc.update("INSERT INTO ai_prompt_definition (id,prompt_key,scope,owner_agent_definition_id,name,description,stage_key,status,created_by,created_at,updated_by,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                v.id(), v.promptKey(), v.scope(), v.ownerAgentDefinitionId(), v.name(), v.description(), v.stageKey(), v.status(), v.createdBy(), v.createdAt(), v.updatedBy(), v.updatedAt());
    }
    @Override public List<PromptVersionPO> listPromptVersions(String promptId) {
        return jdbc.query("SELECT * FROM ai_prompt_version WHERE prompt_definition_id=? ORDER BY created_at DESC", PROMPT_VERSION, promptId);
    }
    @Override public PromptVersionPO findPromptVersion(String id) { return one("SELECT * FROM ai_prompt_version WHERE id=?", PROMPT_VERSION, id); }
    @Override public void insertPromptVersion(PromptVersionPO v) {
        jdbc.update("INSERT INTO ai_prompt_version (id,prompt_definition_id,semantic_version,status,checksum,change_summary,created_by,created_at,published_at) VALUES (?,?,?,?,?,?,?,?,?)",
                v.id(), v.promptDefinitionId(), v.semanticVersion(), v.status(), v.checksum(), v.changeSummary(), v.createdBy(), v.createdAt(), v.publishedAt());
    }
    @Override public void updatePromptVersion(PromptVersionPO v) {
        jdbc.update("UPDATE ai_prompt_version SET semantic_version=?,status=?,checksum=?,change_summary=?,published_at=? WHERE id=?",
                v.semanticVersion(), v.status(), v.checksum(), v.changeSummary(), v.publishedAt(), v.id());
    }
    @Override public List<PromptMessageTemplatePO> listPromptMessages(String versionId) {
        return jdbc.query("SELECT * FROM ai_prompt_message_template WHERE prompt_version_id=? ORDER BY ordinal", MESSAGE, versionId);
    }
    @Override public List<PromptVariablePO> listPromptVariables(String versionId) {
        return jdbc.query("SELECT v.* FROM ai_prompt_variable v JOIN ai_prompt_message_template m ON m.id=v.prompt_message_template_id WHERE m.prompt_version_id=? ORDER BY m.ordinal,v.variable_name", VARIABLE, versionId);
    }
    @Override public void replacePromptMessages(
            String versionId, List<PromptMessageTemplatePO> messages,
            List<PromptVariablePO> variables) {
        jdbc.update("DELETE v FROM ai_prompt_variable v JOIN ai_prompt_message_template m ON m.id=v.prompt_message_template_id WHERE m.prompt_version_id=?", versionId);
        jdbc.update("DELETE FROM ai_prompt_message_template WHERE prompt_version_id=?", versionId);
        for (PromptMessageTemplatePO v : messages) {
            jdbc.update("INSERT INTO ai_prompt_message_template (id,prompt_version_id,ordinal,role,message_key,content_template,content_format,trusted_instruction,checksum) VALUES (?,?,?,?,?,?,?,?,?)",
                    v.id(), v.promptVersionId(), v.ordinal(), v.role(), v.messageKey(), v.contentTemplate(), v.contentFormat(), v.trustedInstruction(), v.checksum());
        }
        for (PromptVariablePO v : variables) {
            jdbc.update("INSERT INTO ai_prompt_variable (id,prompt_message_template_id,variable_name,value_type,value_source,required,`sensitive`,max_length,allow_untrusted_content) VALUES (?,?,?,?,?,?,?,?,?)",
                    v.id(), v.promptMessageTemplateId(), v.variableName(), v.valueType(), v.valueSource(), v.required(), v.sensitive(), v.maxLength(), v.allowUntrustedContent());
        }
    }
    @Override public void insertPromptBinding(PromptBindingPO v) {
        jdbc.update("INSERT INTO ai_agent_version_prompt_binding (agent_version_id,stage_key,ordinal,prompt_definition_id,prompt_version_id,required) VALUES (?,?,?,?,?,?)",
                v.agentVersionId(), v.stageKey(), v.ordinal(), v.promptDefinitionId(), v.promptVersionId(), v.required());
    }
    @Override public List<PromptBindingPO> listPromptBindings(String agentVersionId) {
        return jdbc.query("SELECT * FROM ai_agent_version_prompt_binding WHERE agent_version_id=? ORDER BY stage_key,ordinal", PROMPT_BINDING, agentVersionId);
    }

    @Override public AgentVersionPolicyBindingPO findPolicyBinding(String agentVersionId) {
        return one("SELECT * FROM ai_agent_version_policy_binding WHERE agent_version_id=?", POLICY_BINDING, agentVersionId);
    }
    @Override public void upsertModelPolicyBinding(String agentVersionId, String modelPolicyId) {
        jdbc.update("INSERT INTO ai_agent_version_policy_binding (agent_version_id,model_policy_id) VALUES (?,?) ON DUPLICATE KEY UPDATE model_policy_id=VALUES(model_policy_id)", agentVersionId, modelPolicyId);
    }
    @Override public void upsertRagPolicyBinding(String agentVersionId, String ragPolicyId) {
        jdbc.update("INSERT INTO ai_agent_version_policy_binding (agent_version_id,rag_policy_id) VALUES (?,?) ON DUPLICATE KEY UPDATE rag_policy_id=VALUES(rag_policy_id)", agentVersionId, ragPolicyId);
    }
    @Override public void upsertLargeContextModelPolicyBinding(String agentVersionId, String modelPolicyId) {
        jdbc.update("INSERT INTO ai_agent_version_policy_binding (agent_version_id,large_context_model_policy_id) VALUES (?,?) ON DUPLICATE KEY UPDATE large_context_model_policy_id=VALUES(large_context_model_policy_id)", agentVersionId, modelPolicyId);
    }
    @Override public List<AgentVersionKnowledgeBindingPO> listKnowledgeBindings(String agentVersionId) {
        return jdbc.query("SELECT * FROM ai_agent_version_knowledge_binding WHERE agent_version_id=? ORDER BY priority,knowledge_base_id", KNOWLEDGE_BINDING, agentVersionId);
    }
    @Override public void replaceKnowledgeBindings(String agentVersionId, List<AgentVersionKnowledgeBindingPO> values) {
        jdbc.update("DELETE FROM ai_agent_version_knowledge_binding WHERE agent_version_id=?", agentVersionId);
        for (AgentVersionKnowledgeBindingPO v : values) {
            jdbc.update("INSERT INTO ai_agent_version_knowledge_binding (agent_version_id,knowledge_base_id,index_release_id,priority,required) VALUES (?,?,?,?,?)",
                    v.agentVersionId(), v.knowledgeBaseId(), v.indexReleaseId(), v.priority(), v.required());
        }
    }
    @Override public boolean isIndexReleaseReady(String indexReleaseId) {
        Long count = jdbc.queryForObject("SELECT COUNT(*) FROM kb_index_release WHERE id=? AND status='PUBLISHED'", Long.class, indexReleaseId);
        return count != null && count == 1;
    }

    @Override public List<ModelPolicyPO> listModelPolicies(String agentId) { return jdbc.query("SELECT * FROM ai_model_policy WHERE owner_agent_definition_id=? ORDER BY created_at DESC", MODEL, agentId); }
    @Override public ModelPolicyPO findModelPolicy(String id) { return one("SELECT * FROM ai_model_policy WHERE id=?", MODEL, id); }
    @Override public void insertModelPolicy(ModelPolicyPO v) {
        jdbc.update("INSERT INTO ai_model_policy (id,owner_agent_definition_id,policy_key,semantic_version,provider,model_name,temperature,top_p,max_input_tokens,max_output_tokens,connect_timeout_ms,read_timeout_ms,max_retries,status,checksum,created_by,created_at,published_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                v.id(), v.ownerAgentDefinitionId(), v.policyKey(), v.semanticVersion(), v.provider(), v.modelName(), v.temperature(), v.topP(), v.maxInputTokens(), v.maxOutputTokens(), v.connectTimeoutMs(), v.readTimeoutMs(), v.maxRetries(), v.status(), v.checksum(), v.createdBy(), v.createdAt(), v.publishedAt());
    }
    @Override public void updateModelPolicy(ModelPolicyPO v) {
        jdbc.update("UPDATE ai_model_policy SET provider=?,model_name=?,temperature=?,top_p=?,max_input_tokens=?,max_output_tokens=?,connect_timeout_ms=?,read_timeout_ms=?,max_retries=?,status=?,checksum=?,published_at=? WHERE id=?",
                v.provider(), v.modelName(), v.temperature(), v.topP(), v.maxInputTokens(), v.maxOutputTokens(), v.connectTimeoutMs(), v.readTimeoutMs(), v.maxRetries(), v.status(), v.checksum(), v.publishedAt(), v.id());
    }
    @Override public List<RagPolicyPO> listRagPolicies(String agentId) { return jdbc.query("SELECT * FROM ai_rag_policy WHERE owner_agent_definition_id=? ORDER BY created_at DESC", RAG, agentId); }
    @Override public RagPolicyPO findRagPolicy(String id) { return one("SELECT * FROM ai_rag_policy WHERE id=?", RAG, id); }
    @Override public void insertRagPolicy(RagPolicyPO v) {
        jdbc.update("INSERT INTO ai_rag_policy (id,owner_agent_definition_id,policy_key,semantic_version,rewrite_query_limit,vector_top_k,fts_top_k,fusion_top_k,rerank_top_k,context_token_limit,citation_limit,status,checksum,created_by,created_at,published_at,final_evidence_top_k,similarity_candidate_threshold,similarity_pair_limit,adjacent_group_max_parents) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                v.id(), v.ownerAgentDefinitionId(), v.policyKey(), v.semanticVersion(), v.rewriteQueryLimit(), v.vectorTopK(), v.ftsTopK(), v.fusionTopK(), v.rerankTopK(), v.contextTokenLimit(), v.citationLimit(), v.status(), v.checksum(), v.createdBy(), v.createdAt(), v.publishedAt(), v.finalEvidenceTopK(), v.similarityCandidateThreshold(), v.similarityPairLimit(), v.adjacentGroupMaxParents());
    }
    @Override public void updateRagPolicy(RagPolicyPO v) {
        jdbc.update("UPDATE ai_rag_policy SET rewrite_query_limit=?,vector_top_k=?,fts_top_k=?,fusion_top_k=?,rerank_top_k=?,context_token_limit=?,citation_limit=?,status=?,checksum=?,published_at=?,final_evidence_top_k=?,similarity_candidate_threshold=?,similarity_pair_limit=?,adjacent_group_max_parents=? WHERE id=?",
                v.rewriteQueryLimit(), v.vectorTopK(), v.ftsTopK(), v.fusionTopK(), v.rerankTopK(), v.contextTokenLimit(), v.citationLimit(), v.status(), v.checksum(), v.publishedAt(), v.finalEvidenceTopK(), v.similarityCandidateThreshold(), v.similarityPairLimit(), v.adjacentGroupMaxParents(), v.id());
    }

    @Override public AiReleasePO findRelease(String id) {
        return one("SELECT * FROM ai_agent_release WHERE id=?", RELEASE, id);
    }
    @Override public AiReleasePO findActiveRelease(String agentDefinitionId, String environment) {
        return one("SELECT * FROM ai_agent_release WHERE agent_definition_id=? AND environment=? AND release_status='ACTIVE' ORDER BY released_at DESC LIMIT 1", RELEASE, agentDefinitionId, environment);
    }
    @Override public List<AiReleasePO> listReleases(String agentDefinitionId, String environment) {
        return jdbc.query("SELECT * FROM ai_agent_release WHERE agent_definition_id=? AND environment=? ORDER BY created_at DESC", RELEASE, agentDefinitionId, environment);
    }
    @Override public AiReleaseSnapshotPO findReleaseSnapshot(String releaseId) {
        return one("SELECT * FROM ai_agent_release_snapshot WHERE agent_release_id=?", RELEASE_SNAPSHOT, releaseId);
    }
    @Override @Transactional public void insertRelease(AiReleasePO release, AiReleaseSnapshotPO snapshot) {
        jdbc.update("INSERT INTO ai_agent_release (id,agent_definition_id,agent_version_id,environment,release_status,release_snapshot_id,released_by,released_at,rolled_back_from_release_id,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                release.id(), release.agentDefinitionId(), release.agentVersionId(), release.environment(), release.releaseStatus(), release.releaseSnapshotId(), release.releasedBy(), release.releasedAt(), release.rolledBackFromReleaseId(), release.createdAt());
        jdbc.update("INSERT INTO ai_agent_release_snapshot (id,agent_release_id,snapshot_json,checksum,agent_ack_status,agent_ack_at,created_at) VALUES (?,?,?,?,?,?,?)",
                snapshot.id(), snapshot.agentReleaseId(), snapshot.snapshotJson(), snapshot.checksum(), snapshot.agentAckStatus(), snapshot.agentAckAt(), snapshot.createdAt());
    }
    @Override @Transactional public void acknowledgeAndActivateRelease(
            String releaseId, String snapshotId, String agentDefinitionId,
            String environment, String agentVersionId) {
        jdbc.update("UPDATE ai_agent_release SET release_status='RETIRED' WHERE agent_definition_id=? AND environment=? AND release_status='ACTIVE'", agentDefinitionId, environment);
        jdbc.update("UPDATE ai_agent_release_snapshot SET agent_ack_status='ACKNOWLEDGED',agent_ack_at=NOW(6) WHERE id=? AND agent_release_id=?", snapshotId, releaseId);
        jdbc.update("UPDATE ai_agent_release SET release_status='ACTIVE',released_at=NOW(6) WHERE id=? AND release_status='PENDING'", releaseId);
        jdbc.update("UPDATE ai_agent_version SET status='RELEASED',published_at=COALESCE(published_at,NOW(6)) WHERE id=? AND status='VALIDATED'", agentVersionId);
    }

    private <T> T one(String sql, DataClassRowMapper<T> mapper, Object... args) {
        try { return jdbc.queryForObject(sql, mapper, args); }
        catch (EmptyResultDataAccessException ignored) { return null; }
    }
}

package com.aiep.aihub.repository.management;

import com.aiep.aihub.repository.management.AiManagementPOs.AgentDefinitionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.ModelPolicyPO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptBindingPO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptDefinitionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptMessageTemplatePO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptVariablePO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptVersionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.RagPolicyPO;
import java.util.ArrayList;
import java.util.List;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.DataClassRowMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
@ConditionalOnBean(JdbcTemplate.class)
public class JdbcAiManagementMappers implements AiManagementMappers {
    private static final DataClassRowMapper<AgentDefinitionPO> AGENT = DataClassRowMapper.newInstance(AgentDefinitionPO.class);
    private static final DataClassRowMapper<AgentVersionPO> AGENT_VERSION = DataClassRowMapper.newInstance(AgentVersionPO.class);
    private static final DataClassRowMapper<PromptDefinitionPO> PROMPT = DataClassRowMapper.newInstance(PromptDefinitionPO.class);
    private static final DataClassRowMapper<PromptVersionPO> PROMPT_VERSION = DataClassRowMapper.newInstance(PromptVersionPO.class);
    private static final DataClassRowMapper<PromptMessageTemplatePO> MESSAGE = DataClassRowMapper.newInstance(PromptMessageTemplatePO.class);
    private static final DataClassRowMapper<PromptVariablePO> VARIABLE = DataClassRowMapper.newInstance(PromptVariablePO.class);
    private static final DataClassRowMapper<ModelPolicyPO> MODEL = DataClassRowMapper.newInstance(ModelPolicyPO.class);
    private static final DataClassRowMapper<RagPolicyPO> RAG = DataClassRowMapper.newInstance(RagPolicyPO.class);
    private final JdbcTemplate jdbc;

    public JdbcAiManagementMappers(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override public List<AgentDefinitionPO> listAgents() {
        return jdbc.query("SELECT * FROM ai_agent_definition ORDER BY updated_at DESC", AGENT);
    }
    @Override public AgentDefinitionPO findAgent(String id) { return one("SELECT * FROM ai_agent_definition WHERE id=?", AGENT, id); }
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
        jdbc.update("INSERT INTO ai_rag_policy (id,owner_agent_definition_id,policy_key,semantic_version,rewrite_query_limit,vector_top_k,fts_top_k,fusion_top_k,rerank_top_k,context_token_limit,citation_limit,status,checksum,created_by,created_at,published_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                v.id(), v.ownerAgentDefinitionId(), v.policyKey(), v.semanticVersion(), v.rewriteQueryLimit(), v.vectorTopK(), v.ftsTopK(), v.fusionTopK(), v.rerankTopK(), v.contextTokenLimit(), v.citationLimit(), v.status(), v.checksum(), v.createdBy(), v.createdAt(), v.publishedAt());
    }
    @Override public void updateRagPolicy(RagPolicyPO v) {
        jdbc.update("UPDATE ai_rag_policy SET rewrite_query_limit=?,vector_top_k=?,fts_top_k=?,fusion_top_k=?,rerank_top_k=?,context_token_limit=?,citation_limit=?,status=?,checksum=?,published_at=? WHERE id=?",
                v.rewriteQueryLimit(), v.vectorTopK(), v.ftsTopK(), v.fusionTopK(), v.rerankTopK(), v.contextTokenLimit(), v.citationLimit(), v.status(), v.checksum(), v.publishedAt(), v.id());
    }

    private <T> T one(String sql, DataClassRowMapper<T> mapper, Object... args) {
        try { return jdbc.queryForObject(sql, mapper, args); }
        catch (EmptyResultDataAccessException ignored) { return null; }
    }
}

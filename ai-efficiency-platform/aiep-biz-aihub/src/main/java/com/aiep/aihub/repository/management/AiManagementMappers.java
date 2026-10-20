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
import java.util.List;

public interface AiManagementMappers {
    List<AgentDefinitionPO> listAgents();
    AgentDefinitionPO findAgent(String id);
    AgentDefinitionPO findAgentByKey(String agentKey);
    void insertAgent(AgentDefinitionPO value);
    List<AgentVersionPO> listAgentVersions(String agentId);
    AgentVersionPO findAgentVersion(String id);
    void insertAgentVersion(AgentVersionPO value);
    void updateAgentVersion(AgentVersionPO value);

    List<PromptDefinitionPO> listPrompts(String scope, String ownerAgentId);
    PromptDefinitionPO findPromptDefinition(String id);
    void insertPromptDefinition(PromptDefinitionPO value);
    List<PromptVersionPO> listPromptVersions(String promptId);
    PromptVersionPO findPromptVersion(String id);
    void insertPromptVersion(PromptVersionPO value);
    void updatePromptVersion(PromptVersionPO value);
    List<PromptMessageTemplatePO> listPromptMessages(String promptVersionId);
    List<PromptVariablePO> listPromptVariables(String promptVersionId);
    void replacePromptMessages(
            String promptVersionId, List<PromptMessageTemplatePO> messages,
            List<PromptVariablePO> variables);
    void insertPromptBinding(PromptBindingPO value);
    List<PromptBindingPO> listPromptBindings(String agentVersionId);

    AgentVersionPolicyBindingPO findPolicyBinding(String agentVersionId);
    void upsertModelPolicyBinding(String agentVersionId, String modelPolicyId);
    void upsertRagPolicyBinding(String agentVersionId, String ragPolicyId);
    List<AgentVersionKnowledgeBindingPO> listKnowledgeBindings(String agentVersionId);
    void replaceKnowledgeBindings(
            String agentVersionId, List<AgentVersionKnowledgeBindingPO> values);
    boolean isIndexReleaseReady(String indexReleaseId);

    List<ModelPolicyPO> listModelPolicies(String agentId);
    ModelPolicyPO findModelPolicy(String id);
    void insertModelPolicy(ModelPolicyPO value);
    void updateModelPolicy(ModelPolicyPO value);
    List<RagPolicyPO> listRagPolicies(String agentId);
    RagPolicyPO findRagPolicy(String id);
    void insertRagPolicy(RagPolicyPO value);
    void updateRagPolicy(RagPolicyPO value);

    AiReleasePO findRelease(String id);
    AiReleasePO findActiveRelease(String agentDefinitionId, String environment);
    List<AiReleasePO> listReleases(String agentDefinitionId, String environment);
    AiReleaseSnapshotPO findReleaseSnapshot(String releaseId);
    void insertRelease(AiReleasePO release, AiReleaseSnapshotPO snapshot);
    void acknowledgeAndActivateRelease(
            String releaseId, String snapshotId, String agentDefinitionId,
            String environment, String agentVersionId);
}

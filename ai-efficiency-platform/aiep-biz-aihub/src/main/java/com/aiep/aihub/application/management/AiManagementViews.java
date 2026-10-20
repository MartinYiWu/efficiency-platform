package com.aiep.aihub.application.management;

import com.aiep.aihub.repository.management.AiManagementPOs.AgentDefinitionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.ModelPolicyPO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptDefinitionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptMessageTemplatePO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptVariablePO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptVersionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.RagPolicyPO;
import java.util.List;

public final class AiManagementViews {
    private AiManagementViews() {
    }

    public record AgentDetail(AgentDefinitionPO definition, List<AgentVersionPO> versions) { }
    public record PromptDetail(
            PromptDefinitionPO definition, PromptVersionPO version,
            List<PromptMessageTemplatePO> messages, List<PromptVariablePO> variables) { }
    public record PolicyList(List<ModelPolicyPO> modelPolicies, List<RagPolicyPO> ragPolicies) { }
}

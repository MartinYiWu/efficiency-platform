package com.aiep.aihub.application.management;

import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.api.memory.MemoryEpisodeContracts.Content;
import com.aiep.aihub.api.memory.MemoryEpisodeContracts.PromotionCommand;
import com.aiep.aihub.repository.management.AiManagementMappers;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformai.api.dto.MemoryPacketDigest;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.springframework.stereotype.Service;

/** 只适配既有版本化草稿/状态转换；不生成新的发布系统或调用Agent部署接口。 */
@Service
public class MemoryPromotionAssetAdapter {
    private final AiPromptManagementService prompts;private final AiAgentManagementService agents;private final AiManagementMappers repository;
    private static final ObjectMapper JSON=new ObjectMapper().findAndRegisterModules();
    public MemoryPromotionAssetAdapter(AiPromptManagementService prompts,AiAgentManagementService agents,AiManagementMappers repository){this.prompts=prompts;this.agents=agents;this.repository=repository;}
    public record Draft(String versionId,String digest) { }
    public Draft create(IdentityFacade.Subject actor,PromotionCommand command,Content lesson) {
        if(!actor.permissions().contains("memory:promotion:create"))throw new MemoryException("MEMORY_SCOPE_DENIED");
        if("PROMPT".equals(command.targetType())) {
            if(repository.findPromptDefinition(command.targetDefinitionId())==null)throw new MemoryException("MEMORY_PROMOTION_TARGET_INVALID");
            var draft=prompts.createVersion(command.targetDefinitionId(),command.semanticVersion(),MemoryPromotionAssetGuard.MARKER+command.episodeId()+" "+command.changeSummary(),actor.userId());
            String text;
            try{text=JSON.writeValueAsString(lesson);}catch(java.io.IOException invalid){throw new MemoryException("MEMORY_EPISODE_INVALID");}
            prompts.replaceDraft(draft.id(),List.of(new AiPromptManagementService.MessageInput(1,"SYSTEM","reviewed_procedure",text,false)),List.of());
            return new Draft(draft.id(),digest("PROMPT",draft.id()));
        }
        if(!List.of("WORKFLOW","SKILL").contains(command.targetType())||repository.findAgent(command.targetDefinitionId())==null)throw new MemoryException("MEMORY_PROMOTION_TARGET_INVALID");
        var draft=agents.createVersion(command.targetDefinitionId(),command.semanticVersion(),command.graphKey(),command.graphVersion(),MemoryPromotionAssetGuard.MARKER+command.episodeId()+" "+command.changeSummary(),null,actor.userId());
        return new Draft(draft.id(),digest(command.targetType(),draft.id()));
    }
    public String digest(String type,String versionId) {
        Object data;
        if("PROMPT".equals(type)) {
            var detail=prompts.getVersion(versionId);data=List.of(detail.version().id(),detail.version().promptDefinitionId(),detail.version().semanticVersion(),detail.version().checksum(),detail.messages(),detail.variables());
        } else {
            var version=repository.findAgentVersion(versionId);if(version==null)throw new MemoryException("MEMORY_PROMOTION_TARGET_INVALID");
            data=java.util.Arrays.asList(version.id(),version.agentDefinitionId(),version.semanticVersion(),version.graphKey(),version.graphVersion(),repository.findPolicyBinding(versionId),repository.listPromptBindings(versionId),repository.listKnowledgeBindings(versionId));
        }
        return MemoryPacketDigest.canonicalDigest(JSON.valueToTree(data));
    }
    public void publish(IdentityFacade.Subject actor,String type,String versionId,String expectedDigest) {
        if(!actor.permissions().contains("memory:promotion:publish")||!digest(type,versionId).equals(expectedDigest))throw new MemoryException("MEMORY_PROMOTION_ASSET_CHANGED");
        if("PROMPT".equals(type)) {prompts.transition(versionId,"VALIDATED",actor);prompts.transition(versionId,"PUBLISHED",actor);}
        // 原AiReleaseService仅从VALIDATED部署；远端ACK后由原发布事务推进RELEASED。
        else {agents.transition(versionId,"VALIDATED",actor);}
    }
}

package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.repository.memory.MemoryMapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Set;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

/** 显式分域发布；HR只当前事实，不把展示偏好或候选印象送入评分。 */
@Service
public class MemoryAgentPolicyService {
    public static final Set<String> OPERATION_EXPERTS=Set.of("operation.research.insight","operation.channel.content","operation.ip.strategy","operation.quality.review","operation.campaign.plan","operation.user_growth.plan","operation.brand.strategy","operation.product.plan","operation.analytics.review","operation.community.plan","operation.content.create");
    private final boolean enabled;private final MemoryMapper mapper;
    public MemoryAgentPolicyService(@Value("${aiep.memory.agent-policy-binding-enabled:false}") boolean enabled,MemoryMapper mapper){this.enabled=enabled;this.mapper=mapper;}
    public boolean privateMemory(MemoryScopeDTO scope) {
        return privateMemoryDomain(scope.tenantId(),scope.domain());
    }
    public boolean privateMemoryDomain(String tenant,String domain) {
        if("hr".equals(domain))return false;
        if(!enabled)return true;
        var config=config(tenant,domain);
        return config!=null&&config.path("enabled").isBoolean()&&config.path("enabled").booleanValue()
                &&config.path("agentModes").path(domain).isTextual()
                &&"PRIVATE_MEMORY".equals(config.path("agentModes").path(domain).textValue());
    }
    public void requireHrCurrentFacts(String tenant,long skillId) {
        if(skillId<6101||skillId>6110)throw new MemoryException("MEMORY_HR_SKILL_NOT_REGISTERED");
        if(!enabled)return;
        var config=config(tenant,"hr");
        if(config==null||!"CURRENT_FACTS_ONLY".equals(config.path("agentModes").path("hr").asText())
                ||!config.path("hrSkillIds").isArray())throw new MemoryException("FEATURE_DISABLED");
        for(var id:config.path("hrSkillIds"))if(id.isIntegralNumber()&&id.canConvertToLong()&&id.longValue()==skillId)return;
        throw new MemoryException("FEATURE_DISABLED");
    }
    private JsonNode config(String tenant,String domain) {
        var policy=mapper.findPublishedPolicy(MemoryMapper.identity(tenant),domain);
        if(policy==null||!"memory-policy/1".equals(policy.schemaVersion()))return null;
        try{return new ObjectMapper().readTree(policy.policyJson()).path("context");}
        catch(java.io.IOException invalid){throw new MemoryException("MEMORY_POLICY_INVALID");}
    }
}

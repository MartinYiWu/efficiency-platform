package com.aiep.aihub.web.management;

import com.aiep.aihub.application.management.AiAgentManagementService;
import com.aiep.aihub.application.management.AiManagementViews;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentDefinitionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionKnowledgeBindingPO;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionPolicyBindingPO;
import com.aiep.platformcore.api.ApiResponse;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/aihub/agents")
public class AiAgentManagementController {
    private final AiAgentManagementService service;

    public AiAgentManagementController(AiAgentManagementService service) {
        this.service = service;
    }

    @GetMapping
    public ApiResponse<List<AgentDefinitionPO>> list() {
        return ApiResponse.success(service.list());
    }

    @GetMapping("/{id}")
    public ApiResponse<AiManagementViews.AgentDetail> get(@PathVariable String id) {
        return ApiResponse.success(service.get(id));
    }

    @PostMapping
    public ApiResponse<AgentDefinitionPO> create(@RequestBody AgentRequest request) {
        return ApiResponse.success(service.create(
                request.agentKey(), request.name(), request.description(), request.agentType()));
    }

    @PostMapping("/{id}/versions")
    public ApiResponse<AgentVersionPO> createVersion(
            @PathVariable String id, @RequestBody VersionRequest request) {
        return ApiResponse.success(service.createVersion(
                id, request.semanticVersion(), request.graphKey(),
                request.graphVersion(), request.changeSummary(), request.sourceVersionId()));
    }

    @PutMapping("/versions/{id}")
    public ApiResponse<AgentVersionPO> updateVersion(
            @PathVariable String id, @RequestBody VersionRequest request) {
        return ApiResponse.success(service.updateDraft(
                id, request.semanticVersion(), request.graphKey(),
                request.graphVersion(), request.changeSummary()));
    }

    @PostMapping("/versions/{id}/transition")
    public ApiResponse<AgentVersionPO> transition(
            @PathVariable String id, @RequestBody TransitionRequest request) {
        return ApiResponse.success(service.transition(id, request.status()));
    }

    @PutMapping("/versions/{id}/model-policy")
    public ApiResponse<AgentVersionPolicyBindingPO> bindModelPolicy(
            @PathVariable String id, @RequestBody AssetIdRequest request) {
        return ApiResponse.success(service.bindModelPolicy(id, request.assetId()));
    }

    @PutMapping("/versions/{id}/rag-policy")
    public ApiResponse<AgentVersionPolicyBindingPO> bindRagPolicy(
            @PathVariable String id, @RequestBody AssetIdRequest request) {
        return ApiResponse.success(service.bindRagPolicy(id, request.assetId()));
    }

    @PutMapping("/versions/{id}/knowledge-bindings")
    public ApiResponse<List<AgentVersionKnowledgeBindingPO>> bindKnowledge(
            @PathVariable String id, @RequestBody KnowledgeBindingRequest request) {
        return ApiResponse.success(service.bindKnowledge(id, request.bindings()));
    }

    public record AgentRequest(String agentKey, String name, String description, String agentType) { }
    public record VersionRequest(
            String semanticVersion, String graphKey, String graphVersion,
            String changeSummary, String sourceVersionId) { }
    public record TransitionRequest(String status) { }
    public record AssetIdRequest(String assetId) { }
    public record KnowledgeBindingRequest(
            List<AiAgentManagementService.KnowledgeBindingInput> bindings) { }
}

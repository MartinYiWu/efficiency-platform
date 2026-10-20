package com.aiep.aihub.web.management;

import com.aiep.aihub.application.management.AiManagementViews;
import com.aiep.aihub.application.management.AiPromptManagementService;
import com.aiep.aihub.application.management.AiPromptManagementService.MessageInput;
import com.aiep.aihub.application.management.AiPromptManagementService.VariableInput;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptDefinitionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptVersionPO;
import com.aiep.platformcore.api.ApiResponse;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/aihub/prompts")
public class AiPromptManagementController {
    private final AiPromptManagementService service;

    public AiPromptManagementController(AiPromptManagementService service) {
        this.service = service;
    }

    @GetMapping
    public ApiResponse<List<PromptDefinitionPO>> list(
            @RequestParam(required = false) String scope,
            @RequestParam(required = false) String ownerAgentId) {
        return ApiResponse.success(service.list(scope, ownerAgentId));
    }

    @GetMapping("/versions/{id}")
    public ApiResponse<AiManagementViews.PromptDetail> getVersion(@PathVariable String id) {
        return ApiResponse.success(service.getVersion(id));
    }

    @PostMapping
    public ApiResponse<PromptDefinitionPO> create(@RequestBody PromptRequest request) {
        return ApiResponse.success(service.createDefinition(
                request.promptKey(), request.scope(), request.ownerAgentId(), request.name(),
                request.description(), request.stageKey()));
    }

    @PostMapping("/{id}/versions")
    public ApiResponse<PromptVersionPO> createVersion(
            @PathVariable String id, @RequestBody VersionRequest request) {
        return ApiResponse.success(service.createVersion(
                id, request.semanticVersion(), request.changeSummary()));
    }

    @PutMapping("/versions/{id}/content")
    public ApiResponse<PromptVersionPO> replaceContent(
            @PathVariable String id, @RequestBody ContentRequest request) {
        return ApiResponse.success(service.replaceDraft(id, request.messages(), request.variables()));
    }

    @PostMapping("/versions/{id}/transition")
    public ApiResponse<PromptVersionPO> transition(
            @PathVariable String id, @RequestBody TransitionRequest request) {
        return ApiResponse.success(service.transition(id, request.status()));
    }

    @PostMapping("/versions/{id}/bindings")
    public ApiResponse<Map<String, Boolean>> bind(
            @PathVariable String id, @RequestBody BindingRequest request) {
        service.bind(request.agentVersionId(), id, request.stageKey(), request.ordinal(), request.required());
        return ApiResponse.success(Map.of("bound", true));
    }

    public record PromptRequest(
            String promptKey, String scope, String ownerAgentId,
            String name, String description, String stageKey) { }
    public record VersionRequest(String semanticVersion, String changeSummary) { }
    public record ContentRequest(List<MessageInput> messages, List<VariableInput> variables) { }
    public record TransitionRequest(String status) { }
    public record BindingRequest(
            String agentVersionId, String stageKey, int ordinal, boolean required) { }
}

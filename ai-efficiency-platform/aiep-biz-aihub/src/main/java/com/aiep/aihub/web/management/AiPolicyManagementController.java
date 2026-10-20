package com.aiep.aihub.web.management;

import com.aiep.aihub.application.management.AiManagementViews;
import com.aiep.aihub.application.management.AiPolicyManagementService;
import com.aiep.aihub.application.management.AiPolicyManagementService.ModelPolicyInput;
import com.aiep.aihub.application.management.AiPolicyManagementService.RagPolicyInput;
import com.aiep.aihub.repository.management.AiManagementPOs.ModelPolicyPO;
import com.aiep.aihub.repository.management.AiManagementPOs.RagPolicyPO;
import com.aiep.platformcore.api.ApiResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/aihub")
public class AiPolicyManagementController {
    private final AiPolicyManagementService service;

    public AiPolicyManagementController(AiPolicyManagementService service) {
        this.service = service;
    }

    @GetMapping("/policies")
    public ApiResponse<AiManagementViews.PolicyList> list(@RequestParam String agentId) {
        return ApiResponse.success(service.list(agentId));
    }

    @GetMapping("/model-policies/{id}")
    public ApiResponse<ModelPolicyPO> getModel(
            @PathVariable String id, @RequestParam String agentId) {
        return ApiResponse.success(service.getModelPolicy(agentId, id));
    }

    @PostMapping("/model-policies")
    public ApiResponse<ModelPolicyPO> saveModel(@RequestBody ModelPolicyInput request) {
        return ApiResponse.success(service.saveModel(request));
    }

    @PostMapping("/model-policies/{id}/transition")
    public ApiResponse<ModelPolicyPO> transitionModel(
            @PathVariable String id, @RequestBody TransitionRequest request) {
        return ApiResponse.success(service.transitionModel(id, request.status()));
    }

    @GetMapping("/rag-policies/{id}")
    public ApiResponse<RagPolicyPO> getRag(
            @PathVariable String id, @RequestParam String agentId) {
        return ApiResponse.success(service.getRagPolicy(agentId, id));
    }

    @PostMapping("/rag-policies")
    public ApiResponse<RagPolicyPO> saveRag(@RequestBody RagPolicyInput request) {
        return ApiResponse.success(service.saveRag(request));
    }

    @PostMapping("/rag-policies/{id}/transition")
    public ApiResponse<RagPolicyPO> transitionRag(
            @PathVariable String id, @RequestBody TransitionRequest request) {
        return ApiResponse.success(service.transitionRag(id, request.status()));
    }

    public record TransitionRequest(String status) { }
}

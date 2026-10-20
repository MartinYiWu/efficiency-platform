package com.aiep.aihub.web.management;

import com.aiep.aihub.application.management.AiReleaseService;
import com.aiep.aihub.repository.management.AiReleasePO;
import com.aiep.platformcore.api.ApiResponse;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/aihub/agents/{agentKey}")
public class AiReleaseController {
    private final AiReleaseService service;

    public AiReleaseController(AiReleaseService service) {
        this.service = service;
    }

    @PostMapping("/versions/{id}/release")
    public ApiResponse<AiReleasePO> publish(
            @PathVariable String agentKey, @PathVariable String id,
            @RequestBody ReleaseRequest request) {
        return ApiResponse.success(service.publish(agentKey, id, request.environment()));
    }

    @PostMapping("/releases/{id}/rollback")
    public ApiResponse<AiReleasePO> rollback(
            @PathVariable String agentKey, @PathVariable String id) {
        return ApiResponse.success(service.rollback(agentKey, id));
    }

    @GetMapping("/releases")
    public ApiResponse<List<AiReleasePO>> list(
            @PathVariable String agentKey,
            @RequestParam(defaultValue = "dev") String environment) {
        return ApiResponse.success(service.list(agentKey, environment));
    }

    public record ReleaseRequest(String environment) { }
}

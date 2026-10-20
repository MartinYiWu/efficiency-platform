package com.aiep.aihub.web.management;

import com.aiep.aihub.application.customer.CustomerServiceViews.PageView;
import com.aiep.aihub.application.customer.CustomerServiceViews.ReplayView;
import com.aiep.aihub.application.management.AiRunManagementService;
import com.aiep.aihub.repository.customer.CustomerServicePOs.FeedbackPO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.RunPO;
import com.aiep.platformcore.api.ApiResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/aihub")
public class AiRunManagementController {
    private final AiRunManagementService service;
    public AiRunManagementController(AiRunManagementService service) { this.service = service; }
    @GetMapping("/runs")
    public ApiResponse<PageView<RunPO>> runs(@RequestParam(required = false) String agentKey,
            @RequestParam(required = false) String status, @RequestParam(required = false) String answerMode,
            @RequestParam(defaultValue = "1") int page, @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(service.runs(agentKey, status, answerMode, page, pageSize));
    }
    @GetMapping("/runs/{id}/replay")
    public ApiResponse<ReplayView> replay(@PathVariable String id) { return ApiResponse.success(service.replay(id)); }
    @GetMapping("/feedback")
    public ApiResponse<PageView<FeedbackPO>> feedback(@RequestParam(required = false) String rating,
            @RequestParam(required = false) String reasonCode, @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(service.feedback(rating, reasonCode, page, pageSize));
    }
}

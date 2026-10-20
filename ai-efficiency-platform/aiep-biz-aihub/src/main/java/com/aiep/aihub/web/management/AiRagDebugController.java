package com.aiep.aihub.web.management;

import com.aiep.aihub.application.management.AiRagDebugService;
import com.aiep.platformai.api.dto.CustomerServiceDebugView;
import com.aiep.platformcore.api.ApiResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/aihub/rag-debug-runs")
public class AiRagDebugController {
    private final AiRagDebugService service;
    public AiRagDebugController(AiRagDebugService service) { this.service = service; }
    @PostMapping
    public ApiResponse<CustomerServiceDebugView> execute(@RequestBody AiRagDebugService.Request request) {
        return ApiResponse.success(service.execute(request));
    }
    @GetMapping("/{id}")
    public ApiResponse<CustomerServiceDebugView> get(@PathVariable String id) { return ApiResponse.success(service.get(id)); }
}

package com.aiep.aihub.web.memory;

import com.aiep.aihub.api.memory.MemoryContextUsage;
import com.aiep.aihub.application.memory.MemoryContextUsageService;
import com.aiep.platformcore.api.ApiResponse;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/aihub/memory-context")
public class MemoryContextUsageController {
    private final MemoryContextUsageService service;
    public MemoryContextUsageController(MemoryContextUsageService service){this.service=service;}
    @GetMapping public ApiResponse<MemoryContextUsage> read(@RequestParam String topAgent,@RequestParam String sessionId,
            @RequestParam(required=false) String runId) {
        return ApiResponse.success(service.read(topAgent,sessionId,runId)).withTraceId(MemoryExceptionHandler.trace());
    }
    @GetMapping("/summaries/{id}") public ApiResponse<MemoryContextUsage.SegmentDetail> summary(@PathVariable String id,
            @RequestParam String topAgent,@RequestParam String sessionId) {
        return ApiResponse.success(service.summary(topAgent,sessionId,id)).withTraceId(MemoryExceptionHandler.trace());
    }
}

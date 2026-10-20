package com.aiep.knowledge.web;

import com.aiep.knowledge.application.KnowledgeImportService;
import com.aiep.knowledge.application.KnowledgeViews;
import com.aiep.platformcore.api.ApiResponse;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/knowledge")
public class KnowledgeImportController {
    private final KnowledgeImportService service;

    public KnowledgeImportController(KnowledgeImportService service) {
        this.service = service;
    }

    @PostMapping(value = "/bases/{id}/imports", consumes = "multipart/form-data")
    public ApiResponse<KnowledgeViews.IngestBatchView> importFiles(
            @PathVariable String id,
            @RequestPart("files") List<MultipartFile> files,
            @RequestParam(required = false) String directoryId) {
        return ApiResponse.success(service.importFiles(id, directoryId, files));
    }

    @GetMapping("/imports/{batchId}")
    public ApiResponse<KnowledgeViews.IngestBatchView> getBatch(@PathVariable String batchId) {
        return ApiResponse.success(service.getBatch(batchId));
    }

    @PostMapping("/import-items/{itemId}/retry")
    public ApiResponse<KnowledgeViews.IngestItemView> retry(@PathVariable String itemId) {
        return ApiResponse.success(service.retryItem(itemId));
    }
}

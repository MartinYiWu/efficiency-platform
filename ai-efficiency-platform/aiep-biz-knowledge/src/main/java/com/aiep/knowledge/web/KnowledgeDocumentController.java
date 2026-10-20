package com.aiep.knowledge.web;

import com.aiep.knowledge.application.KnowledgeDocumentService;
import com.aiep.knowledge.application.KnowledgeImportService;
import com.aiep.knowledge.application.KnowledgeViews;
import com.aiep.platformcore.api.ApiResponse;
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/knowledge")
public class KnowledgeDocumentController {
    private final KnowledgeDocumentService documents;
    private final KnowledgeImportService imports;

    public KnowledgeDocumentController(KnowledgeDocumentService documents, KnowledgeImportService imports) {
        this.documents = documents;
        this.imports = imports;
    }

    @GetMapping("/bases/{id}/documents")
    public ApiResponse<KnowledgeViews.PageView<KnowledgeViews.DocumentView>> list(
            @PathVariable String id,
            @RequestParam(required = false) String directoryId,
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) String status,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(documents.list(id, directoryId, keyword, status, page, pageSize));
    }

    @PostMapping(value = "/bases/{id}/documents/upload", consumes = "multipart/form-data")
    public ApiResponse<KnowledgeViews.IngestBatchView> upload(
            @PathVariable String id,
            @RequestPart("file") MultipartFile file,
            @RequestParam(required = false) String directoryId) {
        return ApiResponse.success(imports.uploadSingle(id, directoryId, file));
    }

    @GetMapping("/documents/{id}")
    public ApiResponse<KnowledgeViews.DocumentView> getDocument(@PathVariable String id) {
        return ApiResponse.success(documents.getDocument(id));
    }

    @GetMapping("/document-versions/{id}")
    public ApiResponse<KnowledgeViews.DocumentVersionView> getVersion(@PathVariable String id) {
        return ApiResponse.success(documents.getVersion(id));
    }

    @PostMapping(value = "/documents/{id}/versions", consumes = "multipart/form-data")
    public ApiResponse<KnowledgeViews.DocumentVersionView> uploadVersion(
            @PathVariable String id,
            @RequestPart("file") MultipartFile file,
            @ModelAttribute NewVersionRequest request) {
        return ApiResponse.success(documents.uploadVersion(id, file, request.changeSummary(), request.effectiveDate()));
    }

    @GetMapping("/processing-tasks/{id}")
    public ApiResponse<KnowledgeViews.ProcessingTaskView> getTask(@PathVariable String id) {
        return ApiResponse.success(documents.getTask(id));
    }

    @PostMapping("/processing-tasks/{id}/retry")
    public ApiResponse<KnowledgeViews.ProcessingTaskView> retryTask(@PathVariable String id) {
        return ApiResponse.success(documents.retryTask(id));
    }

    public record NewVersionRequest(
            String changeSummary,
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate effectiveDate) { }
}

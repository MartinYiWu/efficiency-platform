package com.aiep.knowledge.web;

import com.aiep.knowledge.application.KnowledgeBaseService;
import com.aiep.knowledge.application.KnowledgeViews;
import com.aiep.platformcore.api.ApiResponse;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/knowledge")
public class KnowledgeBaseController {
    private final KnowledgeBaseService service;

    public KnowledgeBaseController(KnowledgeBaseService service) {
        this.service = service;
    }

    @PostMapping("/bases")
    public ApiResponse<KnowledgeViews.KnowledgeBaseView> create(@RequestBody CreateBaseRequest request) {
        return ApiResponse.success(service.create(request.code(), request.name(), request.description(), request.knowledgeType()));
    }

    @GetMapping("/bases")
    public ApiResponse<KnowledgeViews.PageView<KnowledgeViews.KnowledgeBaseView>> list(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) String knowledgeType,
            @RequestParam(required = false) String status,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(service.list(keyword, knowledgeType, status, page, pageSize));
    }

    @GetMapping("/bases/{id}")
    public ApiResponse<KnowledgeViews.KnowledgeBaseView> get(@PathVariable String id) {
        return ApiResponse.success(service.get(id));
    }

    @PutMapping("/bases/{id}")
    public ApiResponse<KnowledgeViews.KnowledgeBaseView> update(
            @PathVariable String id, @RequestBody UpdateBaseRequest request) {
        return ApiResponse.success(service.update(
                id, request.name(), request.description(), request.knowledgeType(), request.status()));
    }

    @GetMapping("/bases/{id}/directories")
    public ApiResponse<List<KnowledgeViews.DirectoryView>> directories(@PathVariable String id) {
        return ApiResponse.success(service.listDirectories(id));
    }

    @PostMapping("/bases/{id}/directories")
    public ApiResponse<KnowledgeViews.DirectoryView> createDirectory(
            @PathVariable String id, @RequestBody DirectoryRequest request) {
        return ApiResponse.success(service.createDirectory(id, request.parentId(), request.name(), request.sortNo()));
    }

    @PutMapping("/directories/{id}")
    public ApiResponse<KnowledgeViews.DirectoryView> updateDirectory(
            @PathVariable String id, @RequestBody DirectoryUpdateRequest request) {
        return ApiResponse.success(service.updateDirectory(id, request.name(), request.sortNo(), request.status()));
    }

    public record CreateBaseRequest(String code, String name, String description, String knowledgeType) { }
    public record UpdateBaseRequest(String name, String description, String knowledgeType, String status) { }
    public record DirectoryRequest(String parentId, String name, int sortNo) { }
    public record DirectoryUpdateRequest(String name, int sortNo, String status) { }
}

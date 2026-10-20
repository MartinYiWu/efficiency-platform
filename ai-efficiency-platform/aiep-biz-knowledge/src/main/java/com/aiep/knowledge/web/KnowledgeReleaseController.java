package com.aiep.knowledge.web;

import com.aiep.knowledge.application.KnowledgeReleaseService;
import com.aiep.knowledge.application.KnowledgeViews;
import com.aiep.platformcore.api.ApiResponse;
import java.util.List;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/knowledge")
@ConditionalOnBean(KnowledgeReleaseService.class)
public class KnowledgeReleaseController {
    private final KnowledgeReleaseService releases;

    public KnowledgeReleaseController(KnowledgeReleaseService releases) {
        this.releases = releases;
    }

    @PostMapping("/document-versions/{id}/publish")
    public ApiResponse<KnowledgeViews.IndexReleaseView> publish(@PathVariable String id) {
        return ApiResponse.success(releases.publishVersion(id));
    }

    @GetMapping("/bases/{id}/index-releases")
    public ApiResponse<List<KnowledgeViews.IndexReleaseView>> list(@PathVariable String id) {
        return ApiResponse.success(releases.list(id));
    }

    @PostMapping("/index-releases/{id}/rollback")
    public ApiResponse<KnowledgeViews.IndexReleaseView> rollback(@PathVariable String id) {
        return ApiResponse.success(releases.rollback(id));
    }
}

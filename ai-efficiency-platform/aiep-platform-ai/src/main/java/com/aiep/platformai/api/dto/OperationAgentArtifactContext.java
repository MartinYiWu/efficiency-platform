package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.Map;

public record OperationAgentArtifactContext(
        @JsonProperty("artifact_id") String artifactId,
        @JsonProperty("root_artifact_id") String rootArtifactId,
        int version,
        @JsonProperty("artifact_type") String artifactType,
        String scenario,
        String platform,
        String title,
        Map<String, Object> content,
        @JsonProperty("body_markdown") String bodyMarkdown) { }

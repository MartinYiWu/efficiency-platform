package com.aiep.platformfile.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "aiep.file.cos")
public class CosFileProperties {
    private String region = System.getenv("AGENT_COS_REGION");
    private String bucket = System.getenv("AGENT_COS_BUCKET");
    private URI baseUrl = environmentUri("AGENT_COS_BASE_URL");
    private Duration readUrlTtl = Duration.ofMinutes(10);

    public String getRegion() {
        return region;
    }

    public void setRegion(String region) {
        this.region = region;
    }

    public String getBucket() {
        return bucket;
    }

    public void setBucket(String bucket) {
        this.bucket = bucket;
    }

    public URI getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getReadUrlTtl() {
        return readUrlTtl;
    }

    public void setReadUrlTtl(Duration readUrlTtl) {
        this.readUrlTtl = readUrlTtl;
    }

    private static URI environmentUri(String name) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? null : URI.create(value);
    }
}

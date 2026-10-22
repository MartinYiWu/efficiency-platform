package com.aiep.platformfile.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "file.storage.tencent-cos")
public class CosFileProperties {
    private String secretId;
    private String secretKey;
    private String region;
    private String bucket;
    private URI domain;
    private String basePath = "efficiency-platform";
    private Duration readUrlTtl = Duration.ofMinutes(10);

    public String getSecretId() {
        return secretId;
    }

    public void setSecretId(String secretId) {
        this.secretId = secretId;
    }

    public String getSecretKey() {
        return secretKey;
    }

    public void setSecretKey(String secretKey) {
        this.secretKey = secretKey;
    }

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

    public URI getDomain() {
        return domain;
    }

    public void setDomain(URI domain) {
        this.domain = domain;
    }

    public String getBasePath() {
        return basePath;
    }

    public void setBasePath(String basePath) {
        this.basePath = basePath;
    }

    public Duration getReadUrlTtl() {
        return readUrlTtl;
    }

    public void setReadUrlTtl(Duration readUrlTtl) {
        this.readUrlTtl = readUrlTtl;
    }
}

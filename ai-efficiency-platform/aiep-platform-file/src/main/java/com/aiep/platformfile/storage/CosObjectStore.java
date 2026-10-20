package com.aiep.platformfile.storage;

import com.aiep.platformfile.application.FileStorageException;
import com.aiep.platformfile.config.CosFileProperties;
import com.qcloud.cos.COSClient;
import com.qcloud.cos.ClientConfig;
import com.qcloud.cos.auth.BasicCOSCredentials;
import com.qcloud.cos.http.HttpMethodName;
import com.qcloud.cos.model.GeneratePresignedUrlRequest;
import com.qcloud.cos.model.ObjectMetadata;
import com.qcloud.cos.model.PutObjectRequest;
import com.qcloud.cos.region.Region;
import java.net.URI;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;
import org.springframework.stereotype.Component;

/** 腾讯云 COS 的最小受控适配器。凭据只从进程环境读取。 */
@Component
public class CosObjectStore {
    private final CosFileProperties properties;
    private volatile COSClient client;

    public CosObjectStore(CosFileProperties properties) {
        this.properties = properties;
    }

    public void put(String objectKey, Path file, String contentType, long sizeBytes) {
        try {
            ObjectMetadata metadata = new ObjectMetadata();
            metadata.setContentType(contentType);
            metadata.setContentLength(sizeBytes);
            PutObjectRequest request = new PutObjectRequest(
                    required(properties.getBucket(), "bucket"), objectKey, file.toFile());
            request.setMetadata(metadata);
            client().putObject(request);
        } catch (FileStorageException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new FileStorageException("FILE_STORAGE_WRITE_FAILED", "文件对象写入失败", exception);
        }
    }

    public void delete(String objectKey) {
        try {
            client().deleteObject(required(properties.getBucket(), "bucket"), objectKey);
        } catch (FileStorageException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new FileStorageException("FILE_STORAGE_DELETE_FAILED", "文件对象补偿删除失败", exception);
        }
    }

    public URI createReadUrl(String objectKey, Duration ttl) {
        try {
            Date expiresAt = Date.from(Instant.now().plus(ttl));
            GeneratePresignedUrlRequest request = new GeneratePresignedUrlRequest(
                    required(properties.getBucket(), "bucket"), objectKey, HttpMethodName.GET);
            request.setExpiration(expiresAt);
            URI signedUrl = client().generatePresignedUrl(request).toURI();
            validateSignedUrl(signedUrl);
            return signedUrl;
        } catch (FileStorageException exception) {
            throw exception;
        } catch (Exception exception) {
            throw new FileStorageException("FILE_STORAGE_SIGN_FAILED", "文件读取地址生成失败", exception);
        }
    }

    private COSClient client() {
        COSClient current = client;
        if (current != null) {
            return current;
        }
        synchronized (this) {
            if (client == null) {
                String secretId = required(System.getenv("AGENT_COS_SECRET_ID"), "secret id");
                String secretKey = required(System.getenv("AGENT_COS_SECRET_KEY"), "secret key");
                ClientConfig clientConfig = new ClientConfig(new Region(required(properties.getRegion(), "region")));
                client = new COSClient(new BasicCOSCredentials(secretId, secretKey), clientConfig);
            }
            return client;
        }
    }

    private void validateSignedUrl(URI signedUrl) {
        URI configured = properties.getBaseUrl();
        if (configured == null) {
            return;
        }
        if (!"https".equalsIgnoreCase(signedUrl.getScheme())) {
            throw new FileStorageException("FILE_STORAGE_SIGN_FAILED", "文件读取地址必须使用 HTTPS");
        }
        String configuredHost = configured.getHost();
        if (configuredHost != null && !signedUrl.getHost().endsWith(configuredHost)) {
            throw new FileStorageException("FILE_STORAGE_SIGN_FAILED", "文件读取地址与配置域名不匹配");
        }
    }

    private static String required(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new FileStorageException("FILE_STORAGE_CONFIG_INVALID", "COS " + field + " 未配置");
        }
        return value;
    }
}

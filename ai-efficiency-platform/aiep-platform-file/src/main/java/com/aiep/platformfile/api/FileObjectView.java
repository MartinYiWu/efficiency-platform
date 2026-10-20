package com.aiep.platformfile.api;

import java.time.LocalDateTime;

/** 可跨模块使用的文件元数据；对象 Key 不对业务调用方公开。 */
public record FileObjectView(
        String id,
        String tenantId,
        String originalName,
        String contentType,
        long sizeBytes,
        String sha256,
        String status,
        LocalDateTime createdAt) {
}

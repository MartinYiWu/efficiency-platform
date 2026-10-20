package com.aiep.platformfile.api;

import java.net.URI;
import java.time.Duration;
import org.springframework.web.multipart.MultipartFile;

/** Cross-module contract for file metadata and object-storage operations. */
public interface FileFacade {
    FileObjectView store(String tenantId, MultipartFile file);

    FileObjectView get(String tenantId, String fileId);

    URI createReadUrl(String tenantId, String fileId, Duration ttl);
}

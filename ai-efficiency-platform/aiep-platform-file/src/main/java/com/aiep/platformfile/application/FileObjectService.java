package com.aiep.platformfile.application;

import com.aiep.platformfile.api.FileFacade;
import com.aiep.platformfile.api.FileObjectView;
import com.aiep.platformfile.config.CosFileProperties;
import com.aiep.platformfile.repository.FileObjectMapper;
import com.aiep.platformfile.repository.FileObjectPO;
import com.aiep.platformfile.storage.CosObjectStore;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.Reader;
import java.net.URI;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.zip.ZipFile;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

@Service
public class FileObjectService implements FileFacade {
    private static final long MAX_FILE_SIZE = 10L * 1024 * 1024;
    private static final Duration MAX_READ_URL_TTL = Duration.ofHours(1);
    private static final Map<String, Set<String>> TYPES_BY_EXTENSION = Map.of(
            ".pdf", Set.of("application/pdf"),
            ".docx", Set.of("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            ".md", Set.of("text/markdown", "text/x-markdown"),
            ".txt", Set.of("text/plain"),
            ".html", Set.of("text/html"),
            ".htm", Set.of("text/html"));

    private final FileObjectMapper mapper;
    private final CosObjectStore objectStore;
    private final CosFileProperties properties;
    private final Path tempDirectory;

    @Autowired
    public FileObjectService(
            FileObjectMapper mapper,
            CosObjectStore objectStore,
            CosFileProperties properties) {
        this(mapper, objectStore, properties,
                Path.of(System.getProperty("java.io.tmpdir"), "aiep-file-objects"));
    }

    public FileObjectService(
            FileObjectMapper mapper,
            CosObjectStore objectStore,
            CosFileProperties properties,
            Path tempDirectory) {
        this.mapper = mapper;
        this.objectStore = objectStore;
        this.properties = properties;
        this.tempDirectory = tempDirectory;
    }

    @Override
    public FileObjectView store(String tenantId, MultipartFile file) {
        requireTenant(tenantId);
        if (file == null || file.isEmpty()) {
            throw invalid("FILE_EMPTY", "文件不能为空");
        }
        if (file.getSize() > MAX_FILE_SIZE) {
            throw invalid("FILE_TOO_LARGE", "单文件不能超过 10 MiB");
        }

        String originalName = normalizedFileName(file.getOriginalFilename());
        String extension = extension(originalName);
        String declaredType = normalizedContentType(file.getContentType());
        requireDeclaredType(extension, declaredType);

        Path temporaryFile = null;
        try {
            Files.createDirectories(tempDirectory);
            temporaryFile = Files.createTempFile(tempDirectory, "upload-", ".part");
            PreparedFile prepared = copyAndDigest(file, temporaryFile);
            validateContent(temporaryFile, extension);

            String id = UUID.randomUUID().toString();
            String objectKey = objectKey(tenantId, id, extension);
            objectStore.put(objectKey, temporaryFile, declaredType, prepared.sizeBytes());

            FileObjectPO metadata = metadata(id, tenantId, objectKey, originalName, declaredType, prepared);
            try {
                if (mapper.insert(metadata) != 1) {
                    throw new IllegalStateException("文件元数据写入数量不正确");
                }
            } catch (RuntimeException databaseFailure) {
                compensate(objectKey, databaseFailure);
                throw databaseFailure;
            }
            return toView(metadata);
        } catch (RuntimeException exception) {
            throw exception;
        } catch (IOException exception) {
            throw new FileStorageException("FILE_READ_FAILED", "上传文件读取失败", exception);
        } finally {
            deleteTemporaryFile(temporaryFile);
        }
    }

    @Override
    public FileObjectView get(String tenantId, String fileId) {
        return toView(activeFile(tenantId, fileId));
    }

    @Override
    public URI createReadUrl(String tenantId, String fileId, Duration ttl) {
        FileObjectPO file = activeFile(tenantId, fileId);
        Duration effectiveTtl = ttl == null ? properties.getReadUrlTtl() : ttl;
        if (effectiveTtl == null || effectiveTtl.isZero() || effectiveTtl.isNegative()
                || effectiveTtl.compareTo(MAX_READ_URL_TTL) > 0) {
            throw invalid("FILE_READ_TTL_INVALID", "读取地址有效期必须大于 0 且不超过 1 小时");
        }
        return objectStore.createReadUrl(file.getObjectKey(), effectiveTtl);
    }

    private PreparedFile copyAndDigest(MultipartFile source, Path target) throws IOException {
        MessageDigest digest;
        try {
            digest = MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("JVM 不支持 SHA-256", exception);
        }
        long size = 0;
        byte[] buffer = new byte[8192];
        try (InputStream input = source.getInputStream(); OutputStream output = Files.newOutputStream(target)) {
            int count;
            while ((count = input.read(buffer)) != -1) {
                size += count;
                if (size > MAX_FILE_SIZE) {
                    throw invalid("FILE_TOO_LARGE", "单文件不能超过 10 MiB");
                }
                digest.update(buffer, 0, count);
                output.write(buffer, 0, count);
            }
        }
        if (size == 0) {
            throw invalid("FILE_EMPTY", "文件不能为空");
        }
        return new PreparedFile(size, HexFormat.of().formatHex(digest.digest()));
    }

    private void validateContent(Path file, String extension) throws IOException {
        switch (extension) {
            case ".pdf" -> requireMagic(file, new byte[] {'%', 'P', 'D', 'F', '-'});
            case ".docx" -> requireDocx(file);
            case ".md", ".txt" -> requireUtf8Text(file);
            case ".html", ".htm" -> requireHtml(file);
            default -> throw invalid("FILE_TYPE_INVALID", "不支持的文件类型");
        }
    }

    private void requireMagic(Path file, byte[] expected) throws IOException {
        byte[] actual = new byte[expected.length];
        try (InputStream input = Files.newInputStream(file)) {
            if (input.read(actual) != expected.length || !java.util.Arrays.equals(actual, expected)) {
                throw invalid("FILE_TYPE_INVALID", "文件头与声明类型不匹配");
            }
        }
    }

    private void requireDocx(Path file) {
        try (ZipFile zip = new ZipFile(file.toFile())) {
            if (zip.getEntry("[Content_Types].xml") == null || zip.getEntry("word/document.xml") == null) {
                throw invalid("FILE_TYPE_INVALID", "DOCX 结构无效");
            }
        } catch (IOException exception) {
            throw new FileStorageException("FILE_TYPE_INVALID", "DOCX 结构无效", exception);
        }
    }

    private void requireUtf8Text(Path file) throws IOException {
        var decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);
        try (Reader reader = new java.io.InputStreamReader(Files.newInputStream(file), decoder)) {
            char[] buffer = new char[4096];
            int count;
            while ((count = reader.read(buffer)) != -1) {
                for (int index = 0; index < count; index++) {
                    if (buffer[index] == '\0') {
                        throw invalid("FILE_TYPE_INVALID", "文本文件包含二进制内容");
                    }
                }
            }
        } catch (CharacterCodingException exception) {
            throw new FileStorageException("FILE_TYPE_INVALID", "文本文件必须为 UTF-8", exception);
        }
    }

    private void requireHtml(Path file) throws IOException {
        requireUtf8Text(file);
        byte[] prefix = Files.readAllBytes(file);
        String normalized = StandardCharsets.UTF_8.decode(ByteBuffer.wrap(prefix))
                .toString().stripLeading().toLowerCase(Locale.ROOT);
        if (!normalized.startsWith("<!doctype html") && !normalized.startsWith("<html")) {
            throw invalid("FILE_TYPE_INVALID", "HTML 文件头无效");
        }
    }

    private FileObjectPO activeFile(String tenantId, String fileId) {
        requireTenant(tenantId);
        if (fileId == null || fileId.isBlank()) {
            throw invalid("FILE_ID_INVALID", "fileId 不能为空");
        }
        FileObjectPO file = mapper.selectActive(tenantId, fileId);
        if (file == null) {
            throw invalid("FILE_NOT_FOUND", "文件不存在");
        }
        return file;
    }

    private static FileObjectPO metadata(
            String id,
            String tenantId,
            String objectKey,
            String originalName,
            String contentType,
            PreparedFile prepared) {
        LocalDateTime now = LocalDateTime.now();
        FileObjectPO metadata = new FileObjectPO();
        metadata.setId(id);
        metadata.setTenantId(tenantId);
        metadata.setStorageProvider("COS");
        metadata.setObjectKey(objectKey);
        metadata.setOriginalName(originalName);
        metadata.setContentType(contentType);
        metadata.setSizeBytes(prepared.sizeBytes());
        metadata.setSha256(prepared.sha256());
        metadata.setStatus("ACTIVE");
        metadata.setCreatedBy("1");
        metadata.setCreatedAt(now);
        metadata.setUpdatedAt(now);
        return metadata;
    }

    private void compensate(String objectKey, RuntimeException databaseFailure) {
        try {
            objectStore.delete(objectKey);
        } catch (RuntimeException compensationFailure) {
            databaseFailure.addSuppressed(compensationFailure);
        }
    }

    private static void requireDeclaredType(String extension, String contentType) {
        Set<String> allowed = TYPES_BY_EXTENSION.get(extension);
        if (allowed == null || !allowed.contains(contentType)) {
            throw invalid("FILE_TYPE_INVALID", "扩展名、MIME 与支持类型不匹配");
        }
    }

    private static String normalizedFileName(String value) {
        if (value == null || value.isBlank()) {
            throw invalid("FILE_NAME_INVALID", "文件名不能为空");
        }
        String normalized = value.replace('\\', '/');
        normalized = normalized.substring(normalized.lastIndexOf('/') + 1).strip();
        if (normalized.isBlank() || normalized.length() > 500) {
            throw invalid("FILE_NAME_INVALID", "文件名无效");
        }
        return normalized;
    }

    private static String extension(String fileName) {
        int index = fileName.lastIndexOf('.');
        return index < 0 ? "" : fileName.substring(index).toLowerCase(Locale.ROOT);
    }

    private static String normalizedContentType(String contentType) {
        if (contentType == null) {
            return "";
        }
        return contentType.split(";", 2)[0].strip().toLowerCase(Locale.ROOT);
    }

    private static String objectKey(String tenantId, String id, String extension) {
        LocalDate date = LocalDate.now();
        return "customer-service/%s/%04d/%02d/%s%s".formatted(
                tenantId, date.getYear(), date.getMonthValue(), id, extension);
    }

    private static void requireTenant(String tenantId) {
        if (tenantId == null || !tenantId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw invalid("TENANT_ID_INVALID", "tenantId 无效");
        }
    }

    private static FileObjectView toView(FileObjectPO file) {
        return new FileObjectView(
                file.getId(), file.getTenantId(), file.getOriginalName(), file.getContentType(),
                file.getSizeBytes(), file.getSha256(), file.getStatus(), file.getCreatedAt());
    }

    private static FileStorageException invalid(String code, String message) {
        return new FileStorageException(code, message);
    }

    private static void deleteTemporaryFile(Path temporaryFile) {
        if (temporaryFile == null) {
            return;
        }
        try {
            Files.deleteIfExists(temporaryFile);
        } catch (IOException ignored) {
            // 临时文件清理由操作系统最终回收，不改变主链路结果。
        }
    }

    private record PreparedFile(long sizeBytes, String sha256) {
    }
}

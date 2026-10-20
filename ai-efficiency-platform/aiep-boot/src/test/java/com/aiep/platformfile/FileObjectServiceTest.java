package com.aiep.platformfile;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.aiep.platformfile.api.FileObjectView;
import com.aiep.platformfile.application.FileObjectService;
import com.aiep.platformfile.application.FileStorageException;
import com.aiep.platformfile.config.CosFileProperties;
import com.aiep.platformfile.repository.FileObjectMapper;
import com.aiep.platformfile.repository.FileObjectPO;
import com.aiep.platformfile.storage.CosObjectStore;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;
import org.springframework.mock.web.MockMultipartFile;

class FileObjectServiceTest {
    private FileObjectMapper mapper;
    private CosObjectStore objectStore;
    private FileObjectService service;

    @BeforeEach
    void setUp(@TempDir Path tempDirectory) {
        mapper = mock(FileObjectMapper.class);
        objectStore = mock(CosObjectStore.class);
        CosFileProperties properties = new CosFileProperties();
        properties.setReadUrlTtl(Duration.ofMinutes(10));
        service = new FileObjectService(mapper, objectStore, properties, tempDirectory);
    }

    @Test
    void storesValidatedContentWithServerGeneratedKeyAndSha256() {
        when(mapper.insert(any(FileObjectPO.class))).thenReturn(1);
        MockMultipartFile file = new MockMultipartFile(
                "file", "guide.md", "text/markdown", "# 使用指南\n正文".getBytes(StandardCharsets.UTF_8));

        FileObjectView stored = service.store("dev", file);

        ArgumentCaptor<FileObjectPO> metadata = ArgumentCaptor.forClass(FileObjectPO.class);
        verify(mapper).insert(metadata.capture());
        verify(objectStore).put(
                eq(metadata.getValue().getObjectKey()),
                any(Path.class),
                eq(metadata.getValue().getContentType()),
                eq(metadata.getValue().getSizeBytes()));
        assertThat(stored.id()).isNotBlank();
        assertThat(stored.sha256()).hasSize(64);
        assertThat(stored.contentType()).isEqualTo("text/markdown");
        assertThat(metadata.getValue().getObjectKey()).startsWith("customer-service/dev/");
        assertThat(metadata.getValue().getObjectKey()).doesNotContain("guide");
    }

    @Test
    void rejectsFileWhoseHeaderDoesNotMatchDeclaredPdfType() {
        MockMultipartFile file = new MockMultipartFile(
                "file", "fake.pdf", "application/pdf", "not a pdf".getBytes(StandardCharsets.UTF_8));

        assertThatThrownBy(() -> service.store("dev", file))
                .isInstanceOf(FileStorageException.class)
                .extracting("errorCode")
                .isEqualTo("FILE_TYPE_INVALID");
        verify(objectStore, never()).put(any(), any(), any(), anyLong());
        verify(mapper, never()).insert(any(FileObjectPO.class));
    }

    @Test
    void deletesOnlyNewObjectWhenMetadataInsertFails() {
        when(mapper.insert(any(FileObjectPO.class))).thenThrow(new IllegalStateException("db unavailable"));
        MockMultipartFile file = new MockMultipartFile(
                "file", "plain.txt", "text/plain", "company process".getBytes(StandardCharsets.UTF_8));

        assertThatThrownBy(() -> service.store("dev", file))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("db unavailable");

        ArgumentCaptor<String> objectKey = ArgumentCaptor.forClass(String.class);
        verify(objectStore).delete(objectKey.capture());
        assertThat(objectKey.getValue()).startsWith("customer-service/dev/");
    }

    @Test
    void databaseFailureKeepsOriginalErrorWhenCompensationAlsoFails() {
        when(mapper.insert(any(FileObjectPO.class))).thenThrow(new IllegalStateException("db unavailable"));
        doThrow(new IllegalStateException("cos unavailable")).when(objectStore).delete(any());
        MockMultipartFile file = new MockMultipartFile(
                "file", "plain.txt", "text/plain", "company process".getBytes(StandardCharsets.UTF_8));

        assertThatThrownBy(() -> service.store("dev", file))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("db unavailable")
                .satisfies(error -> assertThat(error.getSuppressed())
                        .singleElement()
                        .satisfies(suppressed -> assertThat(suppressed.getMessage())
                                .isEqualTo("cos unavailable")));
    }

    @Test
    void createsReadUrlFromOwnedFileIdUsingConfiguredDefaultTtl() {
        FileObjectPO stored = activeFile("file-1", "customer-service/dev/2026/10/file-1.txt");
        when(mapper.selectActive("dev", "file-1")).thenReturn(stored);
        when(objectStore.createReadUrl(stored.getObjectKey(), Duration.ofMinutes(10)))
                .thenReturn(URI.create("https://objects.invalid/signed"));

        URI readUrl = service.createReadUrl("dev", "file-1", null);

        assertThat(readUrl).isEqualTo(URI.create("https://objects.invalid/signed"));
        verify(objectStore).createReadUrl(stored.getObjectKey(), Duration.ofMinutes(10));
    }

    private FileObjectPO activeFile(String id, String objectKey) {
        FileObjectPO file = new FileObjectPO();
        file.setId(id);
        file.setTenantId("dev");
        file.setStorageProvider("COS");
        file.setObjectKey(objectKey);
        file.setOriginalName("plain.txt");
        file.setContentType("text/plain");
        file.setSizeBytes(10);
        file.setSha256("a".repeat(64));
        file.setStatus("ACTIVE");
        return file;
    }
}

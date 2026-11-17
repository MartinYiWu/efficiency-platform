package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.platformfile.application.EncryptedPrivateFileService;
import com.aiep.platformfile.repository.PrivateFileMapper;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;

class HrPrivateFileBehaviorTest {
  @TempDir Path directory;
  String key = Base64.getEncoder().encodeToString(new byte[32]);

  @Test
  void aes_keeps_plaintext_off_disk_and_cross_tenant_reference_cannot_read() throws Exception {
    var mapper = mock(PrivateFileMapper.class);
    var service = new EncryptedPrivateFileService(mapper, directory.toString(), key);
    byte[] content = "合成私有材料，只作离线验证".getBytes(StandardCharsets.UTF_8);
    var file = service.store("t", "candidate", "s.txt", content);
    var captured = ArgumentCaptor.forClass(PrivateFileMapper.Row.class);
    verify(mapper).insert(captured.capture());
    var row = captured.getValue();
    byte[] encrypted = Files.readAllBytes(directory.resolve(row.objectPath()));
    assertFalse(new String(encrypted, StandardCharsets.UTF_8).contains("合成私有材料"));
    when(mapper.byId("t", file.id())).thenReturn(row);
    when(mapper.authorized("t", "candidate", file.id())).thenReturn(1);
    assertArrayEquals(content, service.read("t", "candidate", file.id()));
    assertThrows(RuntimeException.class, () -> service.read("other", "candidate", file.id()));
  }

  @Test
  void releasing_one_of_two_references_preserves_shared_private_bytes() throws Exception {
    var mapper = mock(PrivateFileMapper.class);
    var service = new EncryptedPrivateFileService(mapper, directory.toString(), key);
    Path bytes = directory.resolve("shared.gcm");
    Files.write(bytes, new byte[] {1, 2, 3});
    var row = new PrivateFileMapper.Row("f", "t", "hash", 3, "s.txt", "shared.gcm", "ACTIVE");
    when(mapper.referenced("t", "one")).thenReturn(List.of(row));
    when(mapper.lock("t", "f")).thenReturn(row);
    when(mapper.references("t", "f")).thenReturn(2L);
    service.release("t", "one");
    assertTrue(Files.exists(bytes));
    verify(mapper, never()).markDeleted(anyString(), anyString());
    verify(mapper).unreferenceFile("t", "one", "f");
  }

  @Test
  void database_insert_failure_compensates_new_encrypted_object() throws Exception {
    var mapper = mock(PrivateFileMapper.class);
    doThrow(new IllegalStateException("synthetic insert failure")).when(mapper).insert(any());
    var service = new EncryptedPrivateFileService(mapper, directory.toString(), key);
    assertThrows(
        RuntimeException.class,
        () ->
            service.store("t", "candidate", "s.txt", "synthetic".getBytes(StandardCharsets.UTF_8)));
    try (var paths = Files.list(directory)) {
      assertEquals(0, paths.count(), "DB插入失败不得遗留无人引用的加密文件");
    }
  }

  @Test
  void delete_metadata_failure_must_not_destroy_still_active_private_file() throws Exception {
    var mapper = mock(PrivateFileMapper.class);
    var service = new EncryptedPrivateFileService(mapper, directory.toString(), key);
    Path bytes = directory.resolve("single.gcm");
    Files.write(bytes, new byte[] {1, 2, 3});
    var row = new PrivateFileMapper.Row("f", "t", "hash", 3, "s.txt", "single.gcm", "ACTIVE");
    when(mapper.referenced("t", "one")).thenReturn(List.of(row));
    when(mapper.lock("t", "f")).thenReturn(row);
    when(mapper.references("t", "f")).thenReturn(1L);
    doThrow(new IllegalStateException("synthetic metadata failure"))
        .when(mapper)
        .markDeleted("t", "f");
    assertThrows(RuntimeException.class, () -> service.release("t", "one"));
    assertTrue(Files.exists(bytes), "未提交删除不得破坏仍ACTIVE原件");
  }
}

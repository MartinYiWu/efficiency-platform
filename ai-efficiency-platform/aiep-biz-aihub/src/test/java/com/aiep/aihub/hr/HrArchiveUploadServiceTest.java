package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;

import com.aiep.aihub.application.hr.*;
import com.fasterxml.jackson.databind.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrArchiveUploadServiceTest {
  ObjectMapper json = new ObjectMapper();

  com.fasterxml.jackson.databind.node.ObjectNode archive(String name, byte[] bytes)
      throws Exception {
    var root = json.createObjectNode();
    root.putArray("documents")
        .addObject()
        .put("filename", name)
        .put("content_base64", Base64.getEncoder().encodeToString(bytes))
        .put(
            "sha256",
            HexFormat.of()
                .formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(bytes)));
    return root;
  }

  @Test
  void preflight_preserves_raw_bytes_and_refuses_hash_path_nested_or_size_before_registration()
      throws Exception {
    byte[] raw = "synthetic".getBytes(StandardCharsets.UTF_8);
    var accepted = HrArchiveUploadService.preflight(archive("folder/resume.txt", raw), 20971520);
    assertEquals("resume.txt", accepted.getFirst().filename());
    assertArrayEquals(raw, accepted.getFirst().content());
    for (String name : List.of("../resume.txt", "C:/resume.txt", "nested.rar"))
      assertThrows(
          HrBusinessException.class,
          () -> HrArchiveUploadService.preflight(archive(name, raw), 20971520));
    var wrong = archive("resume.txt", raw);
    ((com.fasterxml.jackson.databind.node.ObjectNode) wrong.path("documents").get(0))
        .put("sha256", "bad");
    assertThrows(
        HrBusinessException.class, () -> HrArchiveUploadService.preflight(wrong, 20971520));
    assertThrows(
        HrBusinessException.class,
        () -> HrArchiveUploadService.preflight(archive("resume.txt", raw), 1));
  }

  @Test
  void duplicated_basenames_cannot_overwrite_or_partially_import() throws Exception {
    byte[] raw = "synthetic".getBytes(StandardCharsets.UTF_8);
    var input = archive("one/resume.txt", raw);
    ((com.fasterxml.jackson.databind.node.ArrayNode) input.path("documents"))
        .add(archive("two/resume.txt", raw).path("documents").get(0));
    assertThrows(
        HrBusinessException.class, () -> HrArchiveUploadService.preflight(input, 20971520));
  }
}

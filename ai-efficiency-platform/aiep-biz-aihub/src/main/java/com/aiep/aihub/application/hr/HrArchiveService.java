package com.aiep.aihub.application.hr;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.*;
import java.util.zip.*;

/** ZIP先完整预检再原子采用，整个包失败时不写入任何批次条目。 */
public final class HrArchiveService {
  public record Document(String filename, byte[] content) {}

  private HrArchiveService() {}

  public static List<Document> unpack(byte[] content) {
    if (content.length > 100 * 1024 * 1024
        || content.length < 4
        || content[0] != 'P'
        || content[1] != 'K') throw invalid();
    List<Document> result = new ArrayList<>();
    Set<String> names = new HashSet<>();
    long total = 0;
    try (var zip = new ZipInputStream(new ByteArrayInputStream(content), StandardCharsets.UTF_8)) {
      ZipEntry entry;
      while ((entry = zip.getNextEntry()) != null) {
        if (entry.isDirectory()) continue;
        String name = entry.getName().replace('\\', '/');
        String ext = name.substring(name.lastIndexOf('.') + 1).toLowerCase(Locale.ROOT);
        if (name.startsWith("/")
            || name.contains(":")
            || Arrays.asList(name.split("/")).contains("..")
            || name.split("/").length > 8
            || !names.add(name.toLowerCase(Locale.ROOT))
            || Set.of("zip", "rar", "7z", "gz", "tar", "bz2", "xz").contains(ext)) throw invalid();
        var bytes = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int n;
        while ((n = zip.read(buffer)) != -1) {
          if (bytes.size() + n > 20 * 1024 * 1024 || total + n > 500L * 1024 * 1024)
            throw invalid();
          bytes.write(buffer, 0, n);
          total += n;
        }
        if (result.size() >= 100
            || bytes.size() > Math.max(1, entry.getCompressedSize()) * 100
            || total > content.length * 100L) throw invalid();
        result.add(new Document(Path.of(name).getFileName().toString(), bytes.toByteArray()));
      }
    } catch (IOException | IllegalArgumentException e) {
      throw invalid();
    }
    if (result.isEmpty()) throw invalid();
    return List.copyOf(result);
  }

  private static HrBusinessException invalid() {
    return new HrBusinessException("HR_FILE_ARCHIVE_INVALID", "压缩包损坏、嵌套、加密或超过安全上限，请拆分后上传", 422);
  }
}

package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.api.hr.HrBatchContracts.BatchItem;
import com.aiep.aihub.repository.hr.HrBatchMapper;
import com.fasterxml.jackson.databind.*;
import java.nio.file.Path;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** 压缩包CPU解包在事务外，完整预检后短事务登记全部原件，任一失败整批回滚。 */
@Service
public class HrArchiveUploadService {
  private final HrBatchService batches;
  private final HrBatchMapper mapper;
  private final HrBatchLimits limits;
  private final HrSemanticGateway gateway;
  private final ObjectMapper json;
  private final TransactionTemplate transaction;

  public HrArchiveUploadService(
      HrBatchService batches,
      HrBatchMapper mapper,
      HrBatchLimits limits,
      HrSemanticGateway gateway,
      ObjectMapper json,
      PlatformTransactionManager transaction) {
    this.batches = batches;
    this.mapper = mapper;
    this.limits = limits;
    this.gateway = gateway;
    this.json = json;
    this.transaction = new TransactionTemplate(transaction);
  }

  public BatchItem upload(HrActor actor, String id, String filename, byte[] content) {
    String name = HrPositionService.text(filename, 255);
    String extension = name.substring(name.lastIndexOf('.') + 1).toLowerCase(Locale.ROOT);
    if (!Set.of("zip", "rar", "7z").contains(extension))
      return batches.upload(actor, id, name, content);
    batches.get(actor, id);
    var batch = mapper.batch(actor.tenantId(), id);
    if (batch == null) throw HrPositionService.missing();
    HrAccessPolicy.requireFor(
        actor, "hr:candidate:upload", batch.departmentId(), null, "CANDIDATE");
    if (!"DRAFT".equals(batch.status())) throw HrPositionService.conflict();
    var maximum = limits.get(actor, id);
    if (content.length == 0
        || content.length > maximum.maxArchiveBytes()
        || content.length > 104857600) throw HrPositionService.invalid("压缩包超过冻结安全上限");
    var input = json.createObjectNode();
    var extraction = input.putObject("extraction");
    extraction
        .put("filename", name)
        .put("content_base64", Base64.getEncoder().encodeToString(content))
        .put("sha256", hash(content))
        .put("archive_raw", true);
    var output = gateway.execute(actor, 6101, "hr-archive-" + UUID.randomUUID(), input);
    var documents = preflight(output, maximum.maxFileBytes());
    if (mapper.items(actor.tenantId(), id).size() + documents.size()
        > Math.min(batch.maximumItems(), maximum.maxBatchItems()))
      throw HrPositionService.invalid("展开文档数量超过冻结批次上限");
    return transaction.execute(
        status -> {
          var current = mapper.lockBatch(actor.tenantId(), id);
          if (current == null || !"DRAFT".equals(current.status()))
            throw HrPositionService.conflict();
          if (mapper.items(actor.tenantId(), id).size() + documents.size()
              > Math.min(current.maximumItems(), maximum.maxBatchItems()))
            throw HrPositionService.invalid("批次剩余容量不足");
          BatchItem first = null;
          for (var doc : documents) {
            var item = batches.upload(actor, id, doc.filename(), doc.content());
            if (first == null) first = item;
          }
          return first;
        });
  }

  public static List<HrArchiveService.Document> preflight(JsonNode output, long maxFileBytes) {
    if (!output.path("documents").isArray()
        || output.path("documents").isEmpty()
        || output.path("documents").size() > 100) throw invalid();
    List<HrArchiveService.Document> documents = new ArrayList<>();
    Set<String> names = new HashSet<>();
    long total = 0;
    for (var doc : output.path("documents")) {
      String name = doc.path("filename").asText().replace('\\', '/');
      if (name.isBlank()
          || name.length() > 255
          || name.startsWith("/")
          || name.contains(":")
          || Arrays.asList(name.split("/")).contains("..")
          || name.split("/").length > 8) throw invalid();
      String base = Path.of(name).getFileName().toString();
      String ext = base.substring(base.lastIndexOf('.') + 1).toLowerCase(Locale.ROOT);
      if (!Set.of("pdf", "doc", "docx", "jpg", "jpeg", "png", "txt", "md", "html").contains(ext)
          || !names.add(base.toLowerCase(Locale.ROOT))) throw invalid();
      if (!doc.path("content_base64").isTextual()
          || doc.path("content_base64").asText().length() > 27962028) throw invalid();
      byte[] bytes;
      try {
        bytes = Base64.getDecoder().decode(doc.path("content_base64").asText());
      } catch (IllegalArgumentException e) {
        throw invalid();
      }
      total += bytes.length;
      if (bytes.length == 0
          || bytes.length > Math.min(maxFileBytes, 20971520)
          || total > 524288000
          || !hash(bytes).equals(doc.path("sha256").asText())) throw invalid();
      documents.add(new HrArchiveService.Document(base, bytes));
    }
    return List.copyOf(documents);
  }

  private static String hash(byte[] bytes) {
    try {
      return HexFormat.of()
          .formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(bytes));
    } catch (java.security.NoSuchAlgorithmException e) {
      throw new IllegalStateException(e);
    }
  }

  private static HrBusinessException invalid() {
    return new HrBusinessException("HR_FILE_ARCHIVE_INVALID", "压缩包文档清单、哈希或安全边界无效，未采用任何条目", 422);
  }
}

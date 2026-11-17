package com.aiep.platformfile.application;

import com.aiep.platformfile.api.PrivateFileFacade;
import com.aiep.platformfile.repository.PrivateFileMapper;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import javax.crypto.*;
import javax.crypto.spec.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

/** 本机私有制品适配，AES-GCM静态加密，去重仅租户内；无URL和网络回调。 */
@Service
public class EncryptedPrivateFileService implements PrivateFileFacade {
  private final PrivateFileMapper mapper;
  private final Path root;
  private final SecretKeySpec key;
  private PrivateFileFinalizer finalizer;

  @org.springframework.beans.factory.annotation.Autowired
  public EncryptedPrivateFileService(
      PrivateFileMapper mapper,
      @Value("${file.private.root:${user.home}/.aiep/private-files}") String root,
      @Value("${aiep.hr.data-key:}") String encoded,
      PrivateFileFinalizer finalizer) {
    this(mapper, root, encoded);
    this.finalizer = finalizer;
  }

  public EncryptedPrivateFileService(
      PrivateFileMapper mapper,
      @Value("${file.private.root:${user.home}/.aiep/private-files}") String root,
      @Value("${aiep.hr.data-key:}") String encoded) {
    this.mapper = mapper;
    this.root = Path.of(root).toAbsolutePath().normalize();
    if (encoded.isBlank()) key = null;
    else {
      byte[] raw = Base64.getDecoder().decode(encoded);
      if (raw.length != 32) throw new IllegalArgumentException("PRIVATE_FILE_KEY_INVALID");
      key = new SecretKeySpec(raw, "AES");
    }
  }

  @Override
  @org.springframework.transaction.annotation.Transactional
  public synchronized PrivateFile store(
      String tenant, String source, String filename, byte[] content) {
    requireKey();
    if (content.length == 0 || content.length > 100 * 1024 * 1024)
      throw new FileStorageException("PRIVATE_FILE_SIZE_LIMIT", "私有文件大小超限");
    try {
      String hash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(content));
      var row = mapper.byHash(tenant, hash);
      if (row == null) {
        String id = UUID.randomUUID().toString();
        String path = id + ".gcm";
        Files.createDirectories(root);
        byte[] iv = new byte[12];
        new SecureRandom().nextBytes(iv);
        Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
        c.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, iv));
        c.updateAAD(tenant.getBytes(StandardCharsets.UTF_8));
        byte[] encrypted = c.doFinal(content);
        byte[] all = new byte[iv.length + encrypted.length];
        System.arraycopy(iv, 0, all, 0, iv.length);
        System.arraycopy(encrypted, 0, all, iv.length, encrypted.length);
        Path written = resolve(path);
        Files.write(written, all, StandardOpenOption.CREATE_NEW);
        registerRollback(written);
        row = new PrivateFileMapper.Row(id, tenant, hash, content.length, filename, path, "ACTIVE");
        try {
          mapper.insert(row);
        } catch (RuntimeException failure) {
          try {
            Files.deleteIfExists(written);
          } catch (java.io.IOException cleanup) {
            failure.addSuppressed(cleanup);
          }
          throw failure;
        }
      }
      mapper.reference(tenant, source, row.id());
      return new PrivateFile(row.id(), row.hash(), row.sizeBytes(), row.filename());
    } catch (Exception e) {
      if (e instanceof FileStorageException f) throw f;
      throw new FileStorageException("PRIVATE_FILE_WRITE_FAILED", "原件保存失败", e);
    }
  }

  @Override
  public byte[] read(String tenant, String source, String id) {
    requireKey();
    var row = mapper.byId(tenant, id);
    if (row == null || mapper.authorized(tenant, source, id) != 1)
      throw new FileStorageException("PRIVATE_FILE_NOT_FOUND", "原件不存在或不可访问");
    try {
      byte[] all = Files.readAllBytes(resolve(row.objectPath()));
      Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
      c.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, Arrays.copyOf(all, 12)));
      c.updateAAD(tenant.getBytes(StandardCharsets.UTF_8));
      byte[] content = c.doFinal(Arrays.copyOfRange(all, 12, all.length));
      if (content.length != row.sizeBytes()
          || !HexFormat.of()
              .formatHex(MessageDigest.getInstance("SHA-256").digest(content))
              .equals(row.hash())) throw new GeneralSecurityException();
      return content;
    } catch (Exception e) {
      throw new FileStorageException("PRIVATE_FILE_INTEGRITY_FAILED", "原件校验失败", e);
    }
  }

  @Override
  @org.springframework.transaction.annotation.Transactional
  public synchronized void release(String tenant, String source) {
    var rows = mapper.referenced(tenant, source);
    for (var row : rows) {
      mapper.lock(tenant, row.id());
      if (mapper.references(tenant, row.id()) > 1) {
        mapper.unreferenceFile(tenant, source, row.id());
        continue;
      }
      mapper.markDeleted(tenant, row.id());
      Runnable remove = () -> finishDeletion(row);
      if (org.springframework.transaction.support.TransactionSynchronizationManager
          .isSynchronizationActive()) {
        org.springframework.transaction.support.TransactionSynchronizationManager
            .registerSynchronization(
                new org.springframework.transaction.support.TransactionSynchronization() {
                  @Override
                  public void afterCommit() {
                    remove.run();
                  }
                });
      } else remove.run();
    }
  }

  private void registerRollback(Path path) {
    if (org.springframework.transaction.support.TransactionSynchronizationManager
        .isSynchronizationActive())
      org.springframework.transaction.support.TransactionSynchronizationManager
          .registerSynchronization(
              new org.springframework.transaction.support.TransactionSynchronization() {
                @Override
                public void afterCompletion(int status) {
                  if (status != STATUS_COMMITTED)
                    try {
                      Files.deleteIfExists(path);
                    } catch (java.io.IOException ignored) {
                    }
                }
              });
  }

  private void finishDeletion(PrivateFileMapper.Row row) {
    try {
      Files.deleteIfExists(resolve(row.objectPath()));
      if (finalizer == null) {
        mapper.completeDeletion(row.tenantId(), row.id());
        mapper.clearReferences(row.tenantId(), row.id());
      } else finalizer.completed(row.tenantId(), row.id());
    } catch (java.io.IOException e) {
      throw new FileStorageException("PRIVATE_FILE_DELETE_FAILED", "原件清理未完成，已进入持久补偿", e);
    }
  }

  @org.springframework.scheduling.annotation.Scheduled(fixedDelay = 60000)
  public void retryDeletions() {
    for (var row : mapper.pendingDeletions())
      try {
        finishDeletion(row);
      } catch (RuntimeException ignored) {
      }
  }

  private Path resolve(String relative) {
    Path path = root.resolve(relative).normalize();
    if (!path.startsWith(root) || !path.getParent().equals(root))
      throw new FileStorageException("PRIVATE_FILE_PATH_INVALID", "原件路径无效");
    return path;
  }

  private void requireKey() {
    if (key == null) throw new FileStorageException("PRIVATE_FILE_KEY_REQUIRED", "私有原件密钥未配置");
  }
}

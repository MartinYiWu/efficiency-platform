package com.aiep.aihub.application.hr;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** 简历快照采用AES-256-GCM，配置缺失时拒绝处理个人材料而不以明文回退。 */
@Component
public class HrSensitiveJsonCodec {
  private static final byte[] AAD = "hr-private-snapshot/1".getBytes(StandardCharsets.UTF_8);
  private final SecretKeySpec key;

  public HrSensitiveJsonCodec(@Value("${aiep.hr.data-key:}") String base64Key) {
    if (base64Key.isBlank()) {
      key = null;
      return;
    }
    try {
      byte[] decoded = Base64.getDecoder().decode(base64Key);
      if (decoded.length != 32) throw new IllegalArgumentException("invalid key size");
      key = new SecretKeySpec(decoded, "AES");
    } catch (IllegalArgumentException error) {
      throw new HrBusinessException("HR_DATA_KEY_INVALID", "招聘数据加密配置无效", 503);
    }
  }

  public String seal(String plaintext) {
    requireKey();
    try {
      byte[] iv = new byte[12];
      new SecureRandom().nextBytes(iv);
      Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
      cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, iv));
      cipher.updateAAD(AAD);
      return "gcm1:"
          + Base64.getEncoder().encodeToString(iv)
          + ":"
          + Base64.getEncoder()
              .encodeToString(cipher.doFinal(plaintext.getBytes(StandardCharsets.UTF_8)));
    } catch (GeneralSecurityException error) {
      throw new HrBusinessException("HR_DATA_ENCRYPTION_FAILED", "招聘材料加密失败", 503);
    }
  }

  public String open(String sealed) {
    requireKey();
    try {
      String[] parts = sealed.split(":", -1);
      if (parts.length != 3 || !parts[0].equals("gcm1"))
        throw new IllegalArgumentException("invalid envelope");
      byte[] iv = Base64.getDecoder().decode(parts[1]);
      if (iv.length != 12) throw new IllegalArgumentException("invalid nonce");
      Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
      cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, iv));
      cipher.updateAAD(AAD);
      return new String(
          cipher.doFinal(Base64.getDecoder().decode(parts[2])), StandardCharsets.UTF_8);
    } catch (GeneralSecurityException | IllegalArgumentException error) {
      throw new HrBusinessException("HR_DATA_INTEGRITY_FAILED", "招聘材料无法验证，请联系管理员", 503);
    }
  }

  public String searchKey(String tenant, String kind, String value) {
    requireKey();
    try {
      javax.crypto.Mac mac = javax.crypto.Mac.getInstance("HmacSHA256");
      mac.init(new SecretKeySpec(key.getEncoded(), "HmacSHA256"));
      String normalized =
          java.text.Normalizer.normalize(value, java.text.Normalizer.Form.NFKC)
              .strip()
              .toLowerCase(java.util.Locale.ROOT);
      if ("PHONE".equals(kind)) normalized = normalized.replaceAll("[\\s()\\-]", "");
      return java.util.HexFormat.of()
          .formatHex(
              mac.doFinal(
                  (tenant + ":" + kind + ":" + normalized).getBytes(StandardCharsets.UTF_8)));
    } catch (GeneralSecurityException e) {
      throw new IllegalStateException("HR_IDENTITY_HASH_FAILED");
    }
  }

  private void requireKey() {
    if (key == null) throw new HrBusinessException("HR_DATA_KEY_REQUIRED", "请先配置招聘数据加密密钥", 503);
  }
}

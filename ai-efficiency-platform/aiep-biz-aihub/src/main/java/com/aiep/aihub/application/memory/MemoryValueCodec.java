package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.repository.memory.MemoryMapper;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.*;
import javax.crypto.*;
import javax.crypto.spec.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** 显式keyring；缺失或损坏拒绝使用，不复用HR密钥，不产生随机生产密钥。 */
@Component
public class MemoryValueCodec {
 private final String current;
 private final Map<String,byte[]> keys;
 private final byte[] hmacKey;
 private final SecureRandom random=new SecureRandom();
 public MemoryValueCodec(@Value("${aiep.memory.current-key-version:}") String current,
   @Value("${aiep.memory.encryption-keys:}") String keyring,@Value("${aiep.memory.hmac-key:}") String hmac) {
  this.current=current; Map<String,byte[]> parsed=new HashMap<>(); byte[] mac=null;
  try { var encoded=new ObjectMapper().readValue(keyring,new TypeReference<Map<String,String>>(){});
   for(var e:encoded.entrySet()) {var raw=Base64.getDecoder().decode(e.getValue()); if(raw.length!=32)throw new IllegalArgumentException(); MemoryMapper.aad(new byte[0],new byte[0],new byte[0],e.getKey());parsed.put(e.getKey(),raw);}
   mac=Base64.getDecoder().decode(hmac);if(mac.length<32)throw new IllegalArgumentException();
  }catch(Exception unavailable){parsed.clear();mac=null;}
  this.keys=Map.copyOf(parsed);this.hmacKey=mac;
 }
 public String currentVersion(){require();return current;}
 private void require(){if(hmacKey==null||!keys.containsKey(current))throw new MemoryException("MEMORY_KEY_UNAVAILABLE");}
 public byte[] hmac(byte[] tenant,String... parts){require();try{
  Mac mac=Mac.getInstance("HmacSHA256");mac.init(new SecretKeySpec(hmacKey,"HmacSHA256"));
  mac.update("memory/tenant-hmac/1".getBytes(StandardCharsets.US_ASCII));
  mac.update(ByteBuffer.allocate(4).putInt(tenant.length).array());mac.update(tenant);
  for(String part:parts){byte[] raw=part.getBytes(StandardCharsets.UTF_8);mac.update(ByteBuffer.allocate(4).putInt(raw.length).array());mac.update(raw);}return mac.doFinal();
 }catch(GeneralSecurityException failure){throw new MemoryException("MEMORY_KEY_UNAVAILABLE");}}
 public Sealed seal(byte[] tenant,byte[] item,byte[] version,String value){require();try{
  byte[] nonce=new byte[12];random.nextBytes(nonce);Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");
  cipher.init(Cipher.ENCRYPT_MODE,new SecretKeySpec(keys.get(current),"AES"),new GCMParameterSpec(128,nonce));
  cipher.updateAAD(MemoryMapper.aad(tenant,item,version,current));byte[] all=cipher.doFinal(value.getBytes(StandardCharsets.UTF_8));
  return new Sealed(Arrays.copyOf(all,all.length-16),nonce,Arrays.copyOfRange(all,all.length-16,all.length),hmac(tenant,"value",value),current);
 }catch(GeneralSecurityException failure){throw new MemoryException("MEMORY_KEY_UNAVAILABLE");}}
 public String open(MemoryMapper.VersionRow row){return openSealed(row.tenantId(),row.itemId(),row.id(),new Sealed(row.encryptedPayload(),row.nonce(),row.authTag(),row.contentHmac(),row.keyVersion()));}
 /** 摘要计划/段使用独立AAD对象前缀；调用方先核归属、状态和来源，解密不授予访问权。 */
 public String openSealed(byte[] tenant,byte[] object,byte[] version,Sealed sealed){require();try{
  byte[] key=keys.get(sealed.keyVersion());if(key==null||sealed.payload()==null||sealed.tag()==null||sealed.nonce()==null||sealed.hmac()==null)throw new GeneralSecurityException();
  Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.DECRYPT_MODE,new SecretKeySpec(key,"AES"),new GCMParameterSpec(128,sealed.nonce()));
  cipher.updateAAD(MemoryMapper.aad(tenant,object,version,sealed.keyVersion()));
  byte[] all=ByteBuffer.allocate(sealed.payload().length+sealed.tag().length).put(sealed.payload()).put(sealed.tag()).array();
  String value=new String(cipher.doFinal(all),StandardCharsets.UTF_8);
  if(!MessageDigest.isEqual(sealed.hmac(),hmac(tenant,"value",value)))throw new GeneralSecurityException();return value;
 }catch(GeneralSecurityException|IllegalArgumentException failure){throw new MemoryException("MEMORY_KEY_UNAVAILABLE");}}
 public record Sealed(byte[] payload,byte[] nonce,byte[] tag,byte[] hmac,String keyVersion){}
}

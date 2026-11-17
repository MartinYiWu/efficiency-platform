package com.aiep.platformfile.api;

/** 私有原件只经授权业务内部访问，不返回公共URL；引用独立于底层对象。 */
public interface PrivateFileFacade {
  record PrivateFile(String id, String sha256, long size, String filename) {}

  PrivateFile store(String tenant, String sourceRef, String filename, byte[] content);

  byte[] read(String tenant, String sourceRef, String fileId);

  void release(String tenant, String sourceRef);
}

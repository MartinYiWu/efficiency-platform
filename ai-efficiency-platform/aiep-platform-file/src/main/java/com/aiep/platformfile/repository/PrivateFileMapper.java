package com.aiep.platformfile.repository;

import org.apache.ibatis.annotations.*;

@Mapper
public interface PrivateFileMapper {
  record Row(
      String id,
      String tenantId,
      String hash,
      long sizeBytes,
      String filename,
      String objectPath,
      String status) {}

  Row byHash(@Param("tenant") String tenant, @Param("hash") String hash);

  Row byId(@Param("tenant") String tenant, @Param("id") String id);

  Row lock(@Param("tenant") String tenant, @Param("id") String id);

  void insert(Row row);

  void reference(
      @Param("tenant") String tenant, @Param("source") String source, @Param("file") String file);

  int authorized(
      @Param("tenant") String tenant, @Param("source") String source, @Param("file") String file);

  java.util.List<Row> referenced(@Param("tenant") String tenant, @Param("source") String source);

  void unreference(@Param("tenant") String tenant, @Param("source") String source);

  void unreferenceFile(
      @Param("tenant") String tenant, @Param("source") String source, @Param("file") String file);

  long references(@Param("tenant") String tenant, @Param("file") String file);

  int markDeleted(@Param("tenant") String tenant, @Param("file") String file);

  int completeDeletion(@Param("tenant") String tenant, @Param("file") String file);

  java.util.List<Row> pendingDeletions();

  void clearReferences(@Param("tenant") String tenant, @Param("file") String file);
}

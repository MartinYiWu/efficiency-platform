package com.aiep.identity.repository;

import java.time.Instant;
import java.util.List;
import org.apache.ibatis.annotations.*;

@Mapper
public interface IdentitySessionMapper {
  record SessionRow(String tenantId, String userId) {}

  record GrantRow(String departmentId, String permission, String positionId, String candidateId) {}

  SessionRow session(@Param("hash") String hash, @Param("now") Instant now);

  int activeSessions(
      @Param("tenant") String tenant, @Param("user") String user, @Param("now") Instant now);

  List<GrantRow> grants(@Param("tenant") String tenant, @Param("user") String user);
}

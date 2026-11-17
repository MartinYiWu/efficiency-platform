package com.aiep.aihub.repository.hr;

import java.time.Instant;
import java.util.*;
import org.apache.ibatis.annotations.*;

/** 配置文档头采用CAS，发布内容和审计只追加。 */
@Mapper
public interface HrSettingsMapper {
  record Row(
      String tenantId, String kind, String id, String departmentId, String payload, long version) {}

  record VersionRow(String id, String payload, long version, Instant at) {}

  record AuditRow(
      String id,
      String departmentId,
      String kind,
      String objectId,
      String action,
      String actorId,
      long version,
      Instant at) {}

  Row find(@Param("tenant") String tenant, @Param("kind") String kind, @Param("id") String id);

  List<Row> list(
      @Param("tenant") String tenant,
      @Param("kind") String kind,
      @Param("departments") Set<String> departments);

  int insert(Row row);

  int update(@Param("row") Row row, @Param("expected") long expected);

  void append(
      @Param("tenant") String tenant,
      @Param("kind") String kind,
      @Param("objectId") String objectId,
      @Param("row") VersionRow row);

  List<VersionRow> versions(
      @Param("tenant") String tenant, @Param("kind") String kind, @Param("id") String id);

  void audit(@Param("tenant") String tenant, @Param("row") AuditRow row);

  List<String> candidateIds(
      @Param("tenant") String tenant,
      @Param("department") String department,
      @Param("now") Instant now);

  List<AuditRow> audits(
      @Param("tenant") String tenant, @Param("departments") Set<String> departments);
}

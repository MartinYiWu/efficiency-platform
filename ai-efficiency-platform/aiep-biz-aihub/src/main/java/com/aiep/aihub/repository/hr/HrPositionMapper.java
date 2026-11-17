package com.aiep.aihub.repository.hr;

import java.time.Instant;
import java.util.List;
import java.util.Set;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface HrPositionMapper {
  java.util.List<String> configs(
      @Param("tenant") String tenant, @Param("position") String position);

  int context(
      @Param("tenant") String tenant,
      @Param("position") String position,
      @Param("context") String context,
      @Param("name") String name,
      @Param("normalized") String normalized,
      @Param("level") String level,
      @Param("version") long version);

  java.util.List<PositionRow> listGranted(
      @Param("tenant") String tenant,
      @Param("departments") Set<String> departments,
      @Param("ids") Set<String> ids,
      @Param("grants") java.util.List<com.aiep.aihub.api.hr.HrActor.GrantScope> grants,
      @Param("keyword") String keyword,
      @Param("family") String family,
      @Param("status") String status,
      @Param("offset") int offset,
      @Param("limit") int limit);

  long countGranted(
      @Param("tenant") String tenant,
      @Param("departments") Set<String> departments,
      @Param("ids") Set<String> ids,
      @Param("grants") java.util.List<com.aiep.aihub.api.hr.HrActor.GrantScope> grants,
      @Param("keyword") String keyword,
      @Param("family") String family,
      @Param("status") String status);

  java.util.List<PositionRow> listVisible(
      @org.apache.ibatis.annotations.Param("tenant") String tenant,
      @org.apache.ibatis.annotations.Param("departments") java.util.Set<String> departments,
      @org.apache.ibatis.annotations.Param("ids") java.util.Set<String> ids,
      @org.apache.ibatis.annotations.Param("keyword") String keyword,
      @org.apache.ibatis.annotations.Param("family") String family,
      @org.apache.ibatis.annotations.Param("status") String status,
      @org.apache.ibatis.annotations.Param("offset") int offset,
      @org.apache.ibatis.annotations.Param("limit") int limit);

  long countVisible(
      @org.apache.ibatis.annotations.Param("tenant") String tenant,
      @org.apache.ibatis.annotations.Param("departments") java.util.Set<String> departments,
      @org.apache.ibatis.annotations.Param("ids") java.util.Set<String> ids,
      @org.apache.ibatis.annotations.Param("keyword") String keyword,
      @org.apache.ibatis.annotations.Param("family") String family,
      @org.apache.ibatis.annotations.Param("status") String status);

  record PositionRow(
      String id,
      String tenantId,
      String name,
      String normalizedName,
      String family,
      String departmentId,
      String level,
      String code,
      String status,
      String configVersion,
      String contextVersion,
      String createdBy,
      Instant createdAt,
      long version) {}

  record JsonRow(String positionId, String payload, long version) {}

  void insert(PositionRow row);

  void allocateCode(@Param("tenant") String tenant, @Param("department") String department);

  long currentCode(@Param("tenant") String tenant, @Param("department") String department);

  PositionRow find(@Param("tenant") String tenant, @Param("id") String id);

  List<PositionRow> list(
      @Param("tenant") String tenant,
      @Param("departments") Set<String> departments,
      @Param("keyword") String keyword,
      @Param("family") String family,
      @Param("status") String status,
      @Param("offset") int offset,
      @Param("limit") int limit);

  long count(
      @Param("tenant") String tenant,
      @Param("departments") Set<String> departments,
      @Param("keyword") String keyword,
      @Param("family") String family,
      @Param("status") String status);

  JsonRow draft(@Param("tenant") String tenant, @Param("positionId") String positionId);

  int advanceDraft(
      @Param("tenant") String tenant,
      @Param("positionId") String positionId,
      @Param("expected") long expected);

  void writeDraft(
      @Param("tenant") String tenant,
      @Param("positionId") String positionId,
      @Param("payload") String payload,
      @Param("version") long version);

  void insertConfig(
      @Param("tenant") String tenant,
      @Param("id") String id,
      @Param("positionId") String positionId,
      @Param("configVersion") String configVersion,
      @Param("payload") String payload,
      @Param("hash") String hash);

  String config(
      @Param("tenant") String tenant,
      @Param("positionId") String positionId,
      @Param("configVersion") String configVersion);

  int activate(
      @Param("tenant") String tenant,
      @Param("id") String id,
      @Param("configVersion") String configVersion,
      @Param("contextVersion") String contextVersion,
      @Param("expected") long expected);

  int disable(
      @Param("tenant") String tenant, @Param("id") String id, @Param("expected") long expected);

  int metadata(
      @Param("tenant") String tenant,
      @Param("id") String id,
      @Param("configVersion") String configVersion,
      @Param("name") String name,
      @Param("normalizedName") String normalizedName,
      @Param("level") String level);

  int staleResults(
      @Param("tenant") String tenant,
      @Param("id") String id,
      @Param("configVersion") String configVersion);
}

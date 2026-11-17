package com.aiep.aihub.repository.hr;

import com.aiep.aihub.api.hr.HrPositionContracts.ConfigVersion;
import com.aiep.aihub.api.hr.HrPositionContracts.Draft;
import com.aiep.aihub.api.hr.HrPositionContracts.Position;
import java.util.List;
import java.util.Set;

public interface HrPositionRepository {
  default java.util.List<ConfigVersion> configs(String tenant, String position) {
    throw new IllegalStateException("HR_VERSION_QUERY_NOT_READY");
  }

  default boolean context(
      String tenant, String position, String context, String name, String level, long version) {
    throw new IllegalStateException("HR_CONTEXT_WRITE_NOT_READY");
  }

  default List<Position> listGranted(
      com.aiep.aihub.api.hr.HrActor actor,
      String keyword,
      String family,
      String status,
      int offset,
      int limit) {
    if (actor.authenticated()) throw new IllegalStateException("HR_GRANT_TUPLE_REQUIRED");
    return listVisible(
        actor.tenantId(),
        actor.departmentIds(),
        actor.positionIds(),
        keyword,
        family,
        status,
        offset,
        limit);
  }

  default long countGranted(
      com.aiep.aihub.api.hr.HrActor actor, String keyword, String family, String status) {
    if (actor.authenticated()) throw new IllegalStateException("HR_GRANT_TUPLE_REQUIRED");
    return countVisible(
        actor.tenantId(), actor.departmentIds(), actor.positionIds(), keyword, family, status);
  }

  default List<Position> listVisible(
      String tenantId,
      Set<String> departments,
      Set<String> ids,
      String keyword,
      String family,
      String status,
      int offset,
      int limit) {
    if (!ids.contains("*")) throw new IllegalStateException("HR_OBJECT_SCOPE_REQUIRED");
    return list(tenantId, departments, keyword, family, status, offset, limit);
  }

  default long countVisible(
      String tenantId,
      Set<String> departments,
      Set<String> ids,
      String keyword,
      String family,
      String status) {
    if (!ids.contains("*")) throw new IllegalStateException("HR_OBJECT_SCOPE_REQUIRED");
    return count(tenantId, departments, keyword, family, status);
  }

  void insert(Position position);

  long nextCode(String tenantId, String departmentId);

  Position find(String tenantId, String id);

  List<Position> list(
      String tenantId,
      Set<String> departments,
      String keyword,
      String family,
      String status,
      int offset,
      int limit);

  long count(
      String tenantId, Set<String> departments, String keyword, String family, String status);

  Draft draft(String tenantId, String positionId);

  boolean saveDraft(String tenantId, Draft draft, long expectedVersion);

  void insertConfig(String tenantId, ConfigVersion config);

  ConfigVersion config(String tenantId, String positionId, String version);

  boolean activate(
      String tenantId,
      String positionId,
      String configVersion,
      String contextVersion,
      long expectedVersion);

  boolean disable(String tenantId, String positionId, long expectedVersion);

  void applyPublishedMetadata(String tenantId, ConfigVersion config);

  void stalePreviousResults(String tenantId, String positionId, String currentVersion);
}

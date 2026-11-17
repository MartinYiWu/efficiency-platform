package com.aiep.aihub.api.hr;

import java.util.List;
import java.util.Set;

/** 服务端主体；正式授权保留完整tuple，集合仅用于展示和粗筛，不能独立决策。 */
public record HrActor(
    String tenantId,
    String userId,
    Set<String> departmentIds,
    Set<String> permissions,
    Set<String> positionIds,
    Set<String> candidateIds,
    boolean authenticated,
    List<GrantScope> grants,
    @com.fasterxml.jackson.annotation.JsonIgnore String sessionRef) {
  public HrActor(
      String tenantId,
      String userId,
      Set<String> departments,
      Set<String> permissions,
      Set<String> positions,
      Set<String> candidates,
      boolean authenticated,
      List<GrantScope> grants) {
    this(
        tenantId,
        userId,
        departments,
        permissions,
        positions,
        candidates,
        authenticated,
        grants,
        null);
  }

  public record GrantScope(
      String permission, String departmentId, String positionId, String candidateId) {}

  public HrActor(String tenantId, String userId, Set<String> departments, Set<String> permissions) {
    this(
        tenantId,
        userId,
        departments,
        permissions,
        Set.of("*"),
        Set.of("*"),
        false,
        List.of(),
        null);
  }

  public HrActor(
      String tenantId,
      String userId,
      Set<String> departments,
      Set<String> permissions,
      Set<String> positions,
      Set<String> candidates) {
    this(tenantId, userId, departments, permissions, positions, candidates, false, List.of(), null);
  }

  public HrActor(
      String tenantId,
      String userId,
      Set<String> departments,
      Set<String> permissions,
      Set<String> positions,
      Set<String> candidates,
      boolean authenticated) {
    this(
        tenantId,
        userId,
        departments,
        permissions,
        positions,
        candidates,
        authenticated,
        List.of(),
        null);
  }

  public HrActor {
    if (tenantId == null || tenantId.isBlank() || userId == null || userId.isBlank())
      throw new IllegalArgumentException("HR_IDENTITY_REQUIRED");
    departmentIds = Set.copyOf(departmentIds);
    permissions = Set.copyOf(permissions);
    positionIds = Set.copyOf(positionIds);
    candidateIds = Set.copyOf(candidateIds);
    grants = List.copyOf(grants);
  }
}

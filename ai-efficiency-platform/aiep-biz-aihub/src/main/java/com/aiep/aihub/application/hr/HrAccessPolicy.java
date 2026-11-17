package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrActor;
import java.util.*;

/** 正式主体采用同一授权tuple决策，不将部门、权限及对象做笛卡尔积。 */
public final class HrAccessPolicy {
  private HrAccessPolicy() {}

  public static void require(HrActor actor, String permission) {
    if (!actor.permissions().contains(permission)
        || actor.authenticated()
            && actor.grants().stream().noneMatch(g -> permission.equals(g.permission())))
      throw denied();
  }

  public static Set<String> departmentsFor(HrActor actor, String permission) {
    require(actor, permission);
    if (!actor.authenticated()) return actor.departmentIds();
    return actor.grants().stream()
        .filter(
            g ->
                permission.equals(g.permission())
                    && g.departmentId() != null
                    && actor.departmentIds().contains(g.departmentId()))
        .map(HrActor.GrantScope::departmentId)
        .collect(java.util.stream.Collectors.toUnmodifiableSet());
  }

  public static Set<String> objectIdsFor(
      HrActor actor, String permission, String department, String kind) {
    require(actor, permission);
    if (!actor.authenticated())
      return "POSITION".equals(kind) ? actor.positionIds() : actor.candidateIds();
    return actor.grants().stream()
        .filter(
            g -> permission.equals(g.permission()) && Objects.equals(department, g.departmentId()))
        .map(g -> "POSITION".equals(kind) ? g.positionId() : g.candidateId())
        .filter(Objects::nonNull)
        .collect(java.util.stream.Collectors.toUnmodifiableSet());
  }

  public static void requireFor(
      HrActor actor, String permission, String department, String objectId, String kind) {
    require(actor, permission);
    department(actor, department);
    if (!actor.authenticated()) {
      if ("POSITION".equals(kind) && objectId != null) position(actor, objectId);
      if ("CANDIDATE".equals(kind) && objectId != null) candidate(actor, objectId);
      return;
    }
    boolean allowed =
        actor.grants().stream()
            .anyMatch(
                g -> {
                  if (!permission.equals(g.permission())
                      || !Objects.equals(department, g.departmentId())) return false;
                  if ("POSITION".equals(kind))
                    return objectId == null
                        ? g.positionId() != null
                        : scope(g.positionId(), objectId);
                  if ("CANDIDATE".equals(kind))
                    return objectId == null
                        ? g.candidateId() != null
                        : scope(g.candidateId(), objectId);
                  return unscoped(g.positionId()) && unscoped(g.candidateId());
                });
    if (!allowed) throw missing();
  }

  private static boolean scope(String scope, String id) {
    return "*".equals(scope) || Objects.equals(scope, id);
  }

  private static boolean unscoped(String value) {
    return value == null || "*".equals(value);
  }

  public static void department(HrActor actor, String id) {
    if (id == null || !actor.departmentIds().contains(id)) throw missing();
  }

  public static void position(HrActor actor, String id) {
    if (!actor.positionIds().contains("*") && !actor.positionIds().contains(id)) throw missing();
  }

  public static void candidate(HrActor actor, String id) {
    if (!actor.candidateIds().contains("*") && !actor.candidateIds().contains(id)) throw missing();
  }

  private static HrBusinessException denied() {
    return new HrBusinessException("HR_PERMISSION_DENIED", "没有执行此操作的权限", 403);
  }

  private static HrBusinessException missing() {
    return new HrBusinessException("HR_OBJECT_NOT_FOUND", "对象不存在或不可访问", 404);
  }
}

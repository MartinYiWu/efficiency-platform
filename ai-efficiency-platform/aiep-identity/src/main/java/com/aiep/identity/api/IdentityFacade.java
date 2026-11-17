package com.aiep.identity.api;

/** Cross-module contract for identity and authorization data. */
public interface IdentityFacade {
  /** 仅接受高熵会话凭据；每次重查有效期与当前授权，空结果代表未认证。 */
  java.util.Optional<Subject> authenticate(String sessionCredential);

  /** 后台阶段重查当前有效会话与授权，不接受业务HTTP自报身份。 */
  default java.util.Optional<Subject> refresh(String tenantId, String userId) {
    return java.util.Optional.empty();
  }

  /** 请求发起的后台任务必须精确核验原不可逆会话引用，不借用账号其他会话。 */
  default java.util.Optional<Subject> refresh(String tenantId, String userId, String sessionRef) {
    return java.util.Optional.empty();
  }

  /** 一条授权的权限、部门、岗位和候选人范围必须关联判断，禁止分别取并集。 */
  record GrantScope(
      String permission, String departmentId, String positionId, String candidateId) {}

  record Subject(
      String tenantId,
      String userId,
      java.util.Set<String> departmentIds,
      java.util.Set<String> permissions,
      java.util.Set<String> positionIds,
      java.util.Set<String> candidateIds,
      java.util.List<GrantScope> grants,
      String sessionRef) {
    public Subject(
        String tenantId,
        String userId,
        java.util.Set<String> departmentIds,
        java.util.Set<String> permissions,
        java.util.Set<String> positionIds,
        java.util.Set<String> candidateIds,
        java.util.List<GrantScope> grants) {
      this(tenantId, userId, departmentIds, permissions, positionIds, candidateIds, grants, null);
    }

    public Subject(
        String tenantId,
        String userId,
        java.util.Set<String> departmentIds,
        java.util.Set<String> permissions,
        java.util.Set<String> positionIds,
        java.util.Set<String> candidateIds) {
      this(
          tenantId,
          userId,
          departmentIds,
          permissions,
          positionIds,
          candidateIds,
          java.util.List.of(),
          null);
    }

    public Subject {
      grants = java.util.List.copyOf(grants);
    }
  }
}

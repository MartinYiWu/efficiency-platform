package com.aiep.aihub.web.hr;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.application.hr.HrBusinessException;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** HR暂未接身份平台时默认关闭；开发身份只能由服务端显式装配，不能信任自报Header。 */
@Component
public class HrActorResolver {
  private final boolean developmentEnabled;
  private final HrActor developmentActor;
  private com.aiep.identity.api.IdentityFacade identity;

  @org.springframework.beans.factory.annotation.Autowired
  public HrActorResolver(
      @Value("${aiep.hr.development-actor.enabled:false}") boolean developmentEnabled,
      @Value("${aiep.hr.development-actor.tenant:}") String tenant,
      @Value("${aiep.hr.development-actor.user:}") String user,
      @Value("${aiep.hr.development-actor.departments:}") String departments,
      @Value("${aiep.hr.development-actor.permissions:}") String permissions,
      com.aiep.identity.api.IdentityFacade identity) {
    this(developmentEnabled, tenant, user, departments, permissions);
    this.identity = identity;
  }

  public HrActorResolver(
      @Value("${aiep.hr.development-actor.enabled:false}") boolean developmentEnabled,
      @Value("${aiep.hr.development-actor.tenant:}") String tenant,
      @Value("${aiep.hr.development-actor.user:}") String user,
      @Value("${aiep.hr.development-actor.departments:}") String departments,
      @Value("${aiep.hr.development-actor.permissions:}") String permissions) {
    this.developmentEnabled = developmentEnabled;
    this.developmentActor =
        developmentEnabled
            ? new HrActor(tenant, user, values(departments), values(permissions))
            : null;
  }

  public HrActor resolve(HttpServletRequest request) {
    String credential = request.getHeader("Authorization");
    if (credential != null && credential.startsWith("Bearer ") && identity != null) {
      var subject = identity.authenticate(credential.substring(7));
      if (subject.isPresent()) {
        var s = subject.get();
        return new HrActor(
            s.tenantId(),
            s.userId(),
            s.departmentIds(),
            s.permissions(),
            s.positionIds(),
            s.candidateIds(),
            true,
            s.grants().stream()
                .map(
                    g ->
                        new HrActor.GrantScope(
                            g.permission(), g.departmentId(), g.positionId(), g.candidateId()))
                .toList(),
            s.sessionRef());
      }
      throw new HrBusinessException("HR_IDENTITY_REQUIRED", "会话无效或已过期", 401);
    }
    Object trusted = request.getAttribute(HrActor.class.getName());
    if (trusted instanceof HrActor actor
        && request.getUserPrincipal() != null
        && actor.userId().equals(request.getUserPrincipal().getName())) return actor;
    if (developmentEnabled && isLoopback(request.getRemoteAddr())) return developmentActor;
    throw new HrBusinessException("HR_IDENTITY_REQUIRED", "请先登录具有招聘数据权限的账号", 401);
  }

  private static boolean isLoopback(String address) {
    return Set.of("127.0.0.1", "::1", "0:0:0:0:0:0:0:1").contains(address);
  }

  private static Set<String> values(String value) {
    return Arrays.stream(value.split(","))
        .map(String::strip)
        .filter(s -> !s.isEmpty())
        .collect(Collectors.toUnmodifiableSet());
  }
}

package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.identity.api.IdentityFacade;
import org.springframework.stereotype.Service;

/** 每个长时阶段重查授权；开发主体不借此获得正式权限。 */
@Service
public class HrActorAuthority {
  private final IdentityFacade identity;

  public HrActorAuthority(IdentityFacade identity) {
    this.identity = identity;
  }

  public HrActor refresh(HrActor actor) {
    if (!actor.authenticated()) return actor;
    if (actor.sessionRef() == null || !actor.sessionRef().matches("[0-9a-f]{64}"))
      throw new HrBusinessException("HR_IDENTITY_REQUIRED", "原会话引用缺失，请重新登录", 401);
    var s =
        identity
            .refresh(actor.tenantId(), actor.userId(), actor.sessionRef())
            .orElseThrow(() -> new HrBusinessException("HR_IDENTITY_REQUIRED", "会话或授权已失效", 401));
    if (!actor.tenantId().equals(s.tenantId())
        || !actor.userId().equals(s.userId())
        || !actor.sessionRef().equals(s.sessionRef()))
      throw new HrBusinessException("HR_IDENTITY_REQUIRED", "身份范围不匹配", 401);
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
}

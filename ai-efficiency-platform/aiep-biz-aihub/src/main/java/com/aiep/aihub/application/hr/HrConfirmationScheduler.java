package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.repository.hr.HrExecutionMapper;
import com.aiep.identity.api.IdentityFacade;
import java.time.Instant;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

/** 人工等待到期不提升事实质量，仅在原授权仍有效时继续，否则持久预算/权限待办。 */
@Service
public class HrConfirmationScheduler {
  private final HrExecutionMapper mapper;
  private final HrBatchService batches;
  private final IdentityFacade identity;

  public HrConfirmationScheduler(
      HrExecutionMapper mapper, HrBatchService batches, IdentityFacade identity) {
    this.mapper = mapper;
    this.batches = batches;
    this.identity = identity;
  }

  @Scheduled(fixedDelay = 60000)
  public void continueDue() {
    for (var due : mapper.dueWaiting(Instant.now())) {
      if (mapper.continueDue(due.tenantId(), due.candidateId(), Instant.now()) != 1) continue;
      try {
        var s =
            identity
                .refresh(due.tenantId(), due.userId())
                .orElseThrow(() -> new HrBusinessException("HR_IDENTITY_REQUIRED", "授权已失效", 401));
        var actor =
            new HrActor(
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
                    .toList());
        batches.continueCandidate(
            actor, due.candidateId(), due.version(), "auto-" + due.candidateId());
      } catch (HrBusinessException e) {
        mapper.waitingState(
            due.tenantId(),
            due.candidateId(),
            e.status() == 401 || e.status() == 403 || e.status() == 404
                ? "BLOCKED_PERMISSION"
                : "BLOCKED_BUDGET");
      } catch (RuntimeException e) {
        mapper.waitingState(due.tenantId(), due.candidateId(), "BLOCKED_SYSTEM");
      }
    }
  }
}

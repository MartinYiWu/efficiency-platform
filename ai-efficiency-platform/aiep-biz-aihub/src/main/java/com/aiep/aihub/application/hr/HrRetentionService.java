package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrTalentContracts.*;
import com.aiep.aihub.repository.hr.HrTalentMapper;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 只允许有新法律依据的显式延期；访问、标签和重算永不续期。 */
@Service
public class HrRetentionService {
  private final HrTalentMapper mapper;
  private final HrTalentSearchService talent;
  private final HrAuditService audit;

  public HrRetentionService(
      HrTalentMapper mapper, HrTalentSearchService talent, HrAuditService audit) {
    this.mapper = mapper;
    this.talent = talent;
    this.audit = audit;
  }

  @Transactional
  public void extend(HrActor actor, String id, RetentionExtension request) {
    var c = talent.authorized(actor, id, "hr:candidate:retention");
    HrCandidateMergeService.reason(request.legalBasis());
    if (request.expiresAt() == null
        || !request.expiresAt().isAfter(c.expiresAt())
        || request
            .expiresAt()
            .isAfter(Instant.now().atZone(ZoneId.of("Asia/Shanghai")).plusMonths(60).toInstant())
        || request.policyVersion() == null
        || mapper.policy(actor.tenantId(), request.policyVersion()) == null)
      throw HrTalentSearchService.invalid();
    if (mapper.extend(
            actor.tenantId(),
            id,
            request.expectedVersion(),
            request.expiresAt(),
            request.policyVersion())
        != 1) throw HrCandidateMergeService.conflict();
    audit.append(actor, "RETENTION_EXTENDED", id, c.departmentId());
  }
}

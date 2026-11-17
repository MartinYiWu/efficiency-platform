package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrTalentContracts.*;
import com.aiep.aihub.repository.hr.HrTalentMapper;
import java.time.Instant;
import java.util.UUID;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 联系授权30秒一次，读取时重新检查源权限及保留截止。 */
@Service
public class HrContactService {
  private final HrTalentMapper mapper;
  private final HrTalentSearchService talent;
  private final HrAuditService audit;
  private final ObjectProvider<HrContactIdentityPort> identity;

  public HrContactService(
      HrTalentMapper mapper,
      HrTalentSearchService talent,
      HrAuditService audit,
      ObjectProvider<HrContactIdentityPort> identity) {
    this.mapper = mapper;
    this.talent = talent;
    this.audit = audit;
    this.identity = identity;
  }

  @Transactional
  public ContactGrant grant(HrActor actor, String candidateId, ContactRequest request) {
    HrCandidateMergeService.reason(request.reason());
    var c = talent.authorized(actor, candidateId, "hr:candidate:contact");
    if (identity.getIfAvailable() == null) throw unavailable();
    var row =
        new HrTalentMapper.GrantRow(
            UUID.randomUUID().toString(),
            actor.tenantId(),
            candidateId,
            actor.userId(),
            Instant.now().plusSeconds(30),
            "ACTIVE");
    mapper.insertGrant(row);
    audit.append(actor, "CONTACT_GRANT_CREATED", candidateId, c.departmentId());
    return new ContactGrant(row.id(), row.expiresAt());
  }

  @Transactional
  public ContactView read(HrActor actor, String id) {
    var row = mapper.grant(actor.tenantId(), id);
    if (row == null || !actor.userId().equals(row.userId())) throw HrTalentSearchService.missing();
    var c = talent.authorized(actor, row.candidateId(), "hr:candidate:contact");
    var port = identity.getIfAvailable();
    if (port == null) throw unavailable();
    if (mapper.consumeGrant(actor.tenantId(), id, Instant.now()) != 1)
      throw HrTalentSearchService.missing();
    ContactView result = port.read(actor.tenantId(), c.id());
    audit.append(actor, "CONTACT_VIEWED", c.id(), c.departmentId());
    return result;
  }

  private HrBusinessException unavailable() {
    return new HrBusinessException("HR_IDENTITY_NOT_READY", "联系身份域尚未就绪", 503);
  }
}

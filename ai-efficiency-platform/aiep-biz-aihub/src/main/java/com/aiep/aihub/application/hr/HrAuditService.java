package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrTalentContracts.*;
import com.aiep.aihub.repository.hr.HrTalentMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;

/** 审计仅追加非正文事件；subjectRef是不可逆租户墓碑，不记录联系信息或理由原文。 */
@Service
public class HrAuditService {
  private final HrTalentMapper mapper;

  public HrAuditService(HrTalentMapper mapper) {
    this.mapper = mapper;
  }

  public void append(HrActor actor, String action, String subject, String department) {
    mapper.audit(
        actor.tenantId(),
        new AuditEvent(
            UUID.randomUUID().toString(),
            action,
            actor.userId(),
            hash(actor.tenantId() + ":" + subject),
            department,
            Instant.now()));
  }

  public AuditPage list(HrActor actor, int page, int pageSize) {
    HrAccessPolicy.require(actor, "hr:audit:read");
    HrTalentSearchService.pagination(page, pageSize);
    var departments = HrAccessPolicy.departmentsFor(actor, "hr:audit:read");
    departments =
        departments.stream()
            .filter(
                d -> {
                  try {
                    HrAccessPolicy.requireFor(actor, "hr:audit:read", d, null, "CONFIG");
                    return true;
                  } catch (HrBusinessException e) {
                    return false;
                  }
                })
            .collect(java.util.stream.Collectors.toUnmodifiableSet());
    if (departments.isEmpty()) return new AuditPage(List.of(), 0, page, pageSize);
    return new AuditPage(
        mapper.audits(actor.tenantId(), departments, (page - 1) * pageSize, pageSize),
        mapper.auditCount(actor.tenantId(), departments),
        page,
        pageSize);
  }

  public static String hash(String value) {
    try {
      return HexFormat.of()
          .formatHex(
              MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8)));
    } catch (Exception e) {
      throw new IllegalStateException(e);
    }
  }
}

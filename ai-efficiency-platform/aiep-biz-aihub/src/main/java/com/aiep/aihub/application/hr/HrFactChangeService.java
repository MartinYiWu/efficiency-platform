package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.repository.hr.HrPrivacyMapper;
import org.springframework.stereotype.Service;

/** 新事实立即使旧面试产物和下载授权不可用，保留历史内容供有权复核。 */
@Service
public class HrFactChangeService {
  private final HrPrivacyMapper mapper;
  private final HrAuditService audit;

  public HrFactChangeService(HrPrivacyMapper mapper, HrAuditService audit) {
    this.mapper = mapper;
    this.audit = audit;
  }

  public void changed(HrActor actor, String candidate, String department) {
    mapper.staleInterviewSets(actor.tenantId(), candidate);
    mapper.revokeOriginalGrants(actor.tenantId(), candidate);
    mapper.revokeInterviewExports(actor.tenantId(), candidate);
    audit.append(actor, "FACT_SNAPSHOT_CHANGED", candidate, department);
  }
}

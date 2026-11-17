package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrTalentContracts.ContactView;

/** 由真实身份域实现；业务不得通过简历正文猜测联系人或替代认证。 */
public interface HrContactIdentityPort {
  ContactView read(String tenantId, String candidateId);
}

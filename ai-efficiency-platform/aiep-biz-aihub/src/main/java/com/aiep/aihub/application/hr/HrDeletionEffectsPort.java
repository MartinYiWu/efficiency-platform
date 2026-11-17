package com.aiep.aihub.application.hr;

/** 外部删除步骤须有幂等回执；未配置时不得把删除提交冒充清理完成。 */
public interface HrDeletionEffectsPort {
  void deleteIndex(String tenantId, String candidateId, String operationId);

  void releaseFilesAndCaches(String tenantId, String candidateId, String operationId);
}

package com.aiep.aihub.application.hr;

import com.aiep.aihub.repository.hr.HrPrivacyMapper;
import com.aiep.platformfile.api.PrivateFileFacade;
import org.springframework.stereotype.Service;

/** 本模块没有向公共向量库写入候选材料，索引/私有产物各自删除，引用释放保持幂等。 */
@Service
public class HrDeletionEffects implements HrDeletionEffectsPort {
  private final com.aiep.aihub.repository.hr.HrTalentSemanticMapper searches;
  private final com.aiep.aihub.repository.hr.HrSpecialMarksMapper marks;
  private final com.aiep.aihub.repository.hr.HrTalentMapper talent;
  private final com.aiep.aihub.repository.hr.HrTalentIdentityMapper identities;
  private final HrPrivacyMapper mapper;
  private final PrivateFileFacade files;

  public HrDeletionEffects(
      HrPrivacyMapper mapper,
      PrivateFileFacade files,
      com.aiep.aihub.repository.hr.HrTalentIdentityMapper identities,
      com.aiep.aihub.repository.hr.HrTalentMapper talent,
      com.aiep.aihub.repository.hr.HrTalentSemanticMapper searches,
      com.aiep.aihub.repository.hr.HrSpecialMarksMapper marks) {
    this.marks = marks;
    this.searches = searches;
    this.talent = talent;
    this.identities = identities;
    this.mapper = mapper;
    this.files = files;
  }

  @Override
  @org.springframework.transaction.annotation.Transactional
  public void deleteIndex(String tenant, String candidate, String operation) {
    mapper.deleteFeedback(tenant, candidate);
    mapper.deleteEvents(tenant, candidate);
    mapper.deleteResults(tenant, candidate);
    mapper.deleteSemantic(tenant, candidate);
    mapper.deleteRuns(tenant, candidate);
  }

  @Override
  public void releaseFilesAndCaches(String tenant, String candidate, String operation) {
    files.release(tenant, candidate);
    mapper.deleteExports(tenant, candidate);
    talent.deleteGenerations(tenant, candidate);
    mapper.deleteInterviewSets(tenant, candidate);
    mapper.clearBatchContent(tenant, candidate);
    searches.deleteJobsForSource(tenant, candidate);
    searches.deleteSourceRefs(tenant, candidate);
    mapper.deleteSource(tenant, candidate);
    identities.deleteSignals(tenant, candidate);
    identities.deleteAssociations(tenant, candidate);
    marks.deleteForSource(tenant, candidate);
  }
}

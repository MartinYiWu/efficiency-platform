package com.aiep.aihub.repository.hr;

import org.apache.ibatis.annotations.*;

@Mapper
public interface HrPrivacyMapper {
  void staleInterviewSets(@Param("tenant") String tenant, @Param("candidate") String candidate);

  void revokeOriginalGrants(@Param("tenant") String tenant, @Param("candidate") String candidate);

  void revokeInterviewExports(@Param("tenant") String tenant, @Param("candidate") String candidate);

  void deleteFeedback(@Param("tenant") String tenant, @Param("candidate") String candidate);

  void deleteEvents(@Param("tenant") String tenant, @Param("candidate") String candidate);

  void deleteResults(@Param("tenant") String tenant, @Param("candidate") String candidate);

  void deleteSemantic(@Param("tenant") String tenant, @Param("candidate") String candidate);

  void deleteRuns(@Param("tenant") String tenant, @Param("candidate") String candidate);

  void deleteExports(@Param("tenant") String tenant, @Param("candidate") String candidate);

  void deleteInterviewSets(@Param("tenant") String tenant, @Param("candidate") String candidate);

  void clearBatchContent(@Param("tenant") String tenant, @Param("candidate") String candidate);

  void deleteSource(@Param("tenant") String tenant, @Param("candidate") String candidate);
}

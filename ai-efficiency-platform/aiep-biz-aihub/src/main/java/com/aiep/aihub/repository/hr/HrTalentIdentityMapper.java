package com.aiep.aihub.repository.hr;

import java.time.Instant;
import java.util.*;
import org.apache.ibatis.annotations.*;

@Mapper
public interface HrTalentIdentityMapper {
  record Signal(
      String tenantId,
      String candidateId,
      String kind,
      String signalKey,
      int quality,
      boolean sharedContact,
      boolean conflictContact) {}

  record Association(
      String id,
      String tenantId,
      String primaryCandidateId,
      String sourceCandidateId,
      String resumeVersionId,
      String status,
      Instant createdAt) {}

  void signal(Signal signal);

  Set<String> possible(
      @Param("tenant") String tenant,
      @Param("incoming") String incoming,
      @Param("keys") Set<String> keys,
      @Param("departments") Set<String> departments,
      @Param("candidates") Set<String> candidates,
      @Param("now") Instant now);

  void associate(Association row);

  List<Association> associations(
      @Param("tenant") String tenant, @Param("candidate") String candidate);

  void deleteSignals(@Param("tenant") String tenant, @Param("candidate") String candidate);

  void deleteAssociations(@Param("tenant") String tenant, @Param("candidate") String candidate);
}

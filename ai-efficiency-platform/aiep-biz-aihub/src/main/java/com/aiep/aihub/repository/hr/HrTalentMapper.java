package com.aiep.aihub.repository.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.api.hr.HrTalentContracts.*;
import java.time.Instant;
import java.util.*;
import org.apache.ibatis.annotations.*;

/** 来源、不可变题集、授权及删除状态的持久入口。 */
@Mapper
public interface HrTalentMapper {
  List<SetRow> setsVisible(
      @Param("tenant") String tenant,
      @Param("candidate") String candidate,
      @Param("departments") Set<String> departments,
      @Param("positions") Set<String> positions,
      @Param("grants") List<com.aiep.aihub.api.hr.HrActor.GrantScope> grants);

  void freezeGeneration(
      @Param("tenant") String tenant,
      @Param("id") String id,
      @Param("config") String config,
      @Param("provenance") String provenance);

  String generationConfig(@Param("tenant") String tenant, @Param("id") String id);

  void deleteGenerations(@Param("tenant") String tenant, @Param("candidate") String candidate);

  record Waiting(String candidateId, java.time.Instant waitUntil) {}

  List<Waiting> waiting(
      @Param("tenant") String tenant,
      @Param("ids") Set<String> ids,
      @Param("now") java.time.Instant now);

  record MergeRow(
      String id,
      String tenantId,
      String primaryCandidateId,
      String sourceIds,
      String status,
      Instant createdAt,
      Instant revocableUntil,
      long version,
      String createdBy) {}

  record SetRow(
      String id,
      String tenantId,
      String candidateId,
      String positionId,
      long version,
      String status,
      String payload,
      String provenance,
      String cacheKey,
      String createdBy,
      Instant createdAt) {}

  record AssignmentRow(
      String id,
      String tenantId,
      String setId,
      long setVersion,
      String interviewerId,
      Instant expiresAt,
      String status,
      String createdBy) {}

  record GrantRow(
      String id,
      String tenantId,
      String candidateId,
      String userId,
      Instant expiresAt,
      String status) {}

  record JobRow(
      String id,
      String tenantId,
      String candidateId,
      String departmentId,
      String status,
      String step,
      int attempts,
      Instant nextAttemptAt,
      Instant createdAt,
      String failureCode) {}

  record ExportRow(
      String id,
      String tenantId,
      String setId,
      long setVersion,
      String userId,
      String assignmentId,
      String format,
      String payload,
      String grantId,
      Instant expiresAt,
      String status) {}

  List<Candidate> visible(
      @Param("tenant") String tenant,
      @Param("departments") Set<String> departments,
      @Param("candidateIds") Set<String> candidateIds,
      @Param("now") Instant now);

  Set<String> matchedCandidates(@Param("tenant") String tenant, @Param("position") String position);

  Candidate candidate(@Param("tenant") String tenant, @Param("id") String id);

  Candidate lockCandidate(@Param("tenant") String tenant, @Param("id") String id);

  Snapshot snapshot(@Param("tenant") String tenant, @Param("id") String id);

  List<Snapshot> snapshotsByIds(@Param("tenant") String tenant, @Param("ids") Set<String> ids);

  List<com.aiep.aihub.api.hr.HrTalentContracts.FactVersion> factVersions(
      @Param("tenant") String tenant, @Param("sources") Set<String> sources);

  List<com.aiep.aihub.api.hr.HrTalentContracts.MatchingHistory> matchingHistory(
      @Param("tenant") String tenant,
      @Param("sources") Set<String> sources,
      @Param("positions") Set<String> positions);

  String policy(@Param("tenant") String tenant, @Param("id") String id);

  List<Candidate> sources(@Param("tenant") String tenant, @Param("primary") String primary);

  MergeRow mergeForCandidate(@Param("tenant") String tenant, @Param("id") String id);

  MergeRow merge(@Param("tenant") String tenant, @Param("id") String id);

  void insertMerge(MergeRow row);

  int appendMergeSources(
      @Param("tenant") String tenant,
      @Param("id") String id,
      @Param("version") long version,
      @Param("sources") String sources);

  void insertSource(
      @Param("tenant") String tenant,
      @Param("source") String source,
      @Param("primary") String primary,
      @Param("merge") String merge);

  int revokeMerge(
      @Param("tenant") String tenant, @Param("id") String id, @Param("version") long version);

  void revokeSources(@Param("tenant") String tenant, @Param("merge") String merge);

  void staleMixed(@Param("tenant") String tenant, @Param("source") String source);

  void insertSet(SetRow row);

  SetRow set(
      @Param("tenant") String tenant, @Param("id") String id, @Param("version") Long version);

  List<SetRow> sets(@Param("tenant") String tenant, @Param("candidate") String candidate);

  SetRow cached(@Param("tenant") String tenant, @Param("key") String key);

  void insertAssignment(AssignmentRow row);

  AssignmentRow assignment(@Param("tenant") String tenant, @Param("id") String id);

  int revokeAssignment(@Param("tenant") String tenant, @Param("id") String id);

  void insertGrant(GrantRow row);

  GrantRow grant(@Param("tenant") String tenant, @Param("id") String id);

  int consumeGrant(
      @Param("tenant") String tenant, @Param("id") String id, @Param("now") Instant now);

  void audit(@Param("tenant") String tenant, @Param("event") AuditEvent event);

  List<AuditEvent> audits(
      @Param("tenant") String tenant,
      @Param("departments") Set<String> departments,
      @Param("offset") int offset,
      @Param("limit") int limit);

  long auditCount(@Param("tenant") String tenant, @Param("departments") Set<String> departments);

  int tombstone(
      @Param("tenant") String tenant, @Param("id") String id, @Param("version") long version);

  void revokeCandidateGrants(@Param("tenant") String tenant, @Param("candidate") String candidate);

  void insertJob(JobRow row);

  JobRow job(@Param("tenant") String tenant, @Param("id") String id);

  List<JobRow> dueJobs(@Param("now") Instant now);

  int failJob(
      @Param("tenant") String tenant,
      @Param("id") String id,
      @Param("attempts") int attempts,
      @Param("next") Instant next,
      @Param("code") String code);

  int advanceJob(
      @Param("tenant") String tenant,
      @Param("id") String id,
      @Param("oldStep") String oldStep,
      @Param("nextStep") String nextStep);

  void deleteBusiness(@Param("tenant") String tenant, @Param("candidate") String candidate);

  int completeCandidate(@Param("tenant") String tenant, @Param("candidate") String candidate);

  int completeJob(@Param("tenant") String tenant, @Param("id") String id);

  List<Candidate> expired(@Param("now") Instant now);

  void revokeAssignments(@Param("tenant") String tenant, @Param("candidate") String candidate);

  void revokeExports(@Param("tenant") String tenant, @Param("candidate") String candidate);

  int extend(
      @Param("tenant") String tenant,
      @Param("id") String id,
      @Param("version") long version,
      @Param("expires") Instant expires,
      @Param("policy") String policy);

  void insertExport(ExportRow row);

  ExportRow export(@Param("tenant") String tenant, @Param("id") String id);

  ExportRow download(@Param("tenant") String tenant, @Param("grant") String grant);

  int consumeExport(
      @Param("tenant") String tenant, @Param("id") String id, @Param("now") Instant now);

  String operation(
      @Param("tenant") String tenant,
      @Param("actor") String actor,
      @Param("route") String route,
      @Param("key") String key,
      @Param("hash") String hash);

  void insertOperation(
      @Param("tenant") String tenant,
      @Param("actor") String actor,
      @Param("route") String route,
      @Param("key") String key,
      @Param("hash") String hash,
      @Param("result") String result);
}

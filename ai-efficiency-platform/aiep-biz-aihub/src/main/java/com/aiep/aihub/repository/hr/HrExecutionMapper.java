package com.aiep.aihub.repository.hr;

import java.time.Instant;
import java.util.*;
import org.apache.ibatis.annotations.*;

@Mapper
public interface HrExecutionMapper {
  record SourceRow(
      String tenantId,
      String candidateId,
      String policyId,
      String purposes,
      String identityJson,
      String extractionJson,
      String fileId,
      Instant waitUntil,
      String continuationState) {}

  record EventRow(
      String tenantId,
      String runId,
      long sequence,
      String status,
      String resultId,
      String failureCode,
      Instant createdAt) {}

  record FeedbackRow(
      String id,
      String tenantId,
      String resultId,
      String rating,
      String reasonJson,
      String actorId,
      Instant createdAt) {}

  void source(SourceRow row);

  SourceRow sourceByCandidate(@Param("tenant") String tenant, @Param("candidate") String candidate);

  void feedback(FeedbackRow row);

  List<FeedbackRow> feedbacks(@Param("tenant") String tenant, @Param("result") String result);

  void recordEvent(EventRow row);

  List<EventRow> events(
      @Param("tenant") String tenant, @Param("run") String run, @Param("after") long after);

  int recoverRuns(@Param("before") Instant before);

  int recoverBatches(@Param("before") Instant before);

  int recoverItems(@Param("before") Instant before);

  int continueDue(
      @Param("tenant") String tenant,
      @Param("candidate") String candidate,
      @Param("now") Instant now);

  void deleteSource(@Param("tenant") String tenant, @Param("candidate") String candidate);

  void insertLimits(
      @Param("tenant") String tenant,
      @Param("batch") String batch,
      @Param("payload") String payload);

  String getLimits(@Param("tenant") String tenant, @Param("batch") String batch);

  void insertContext(
      @Param("tenant") String tenant,
      @Param("position") String position,
      @Param("version") String version,
      @Param("payload") String payload,
      @Param("hash") String hash,
      @Param("actor") String actor,
      @Param("now") Instant now);

  String getContext(
      @Param("tenant") String tenant,
      @Param("position") String position,
      @Param("version") String version);

  record OriginalGrant(String candidateId, String userId, Instant expiresAt) {}

  void originalGrant(
      @Param("tenant") String tenant,
      @Param("candidate") String candidate,
      @Param("user") String user,
      @Param("id") String id,
      @Param("expires") Instant expires);

  OriginalGrant findOriginalGrant(@Param("tenant") String tenant, @Param("id") String id);

  int consumeOriginalGrant(
      @Param("tenant") String tenant, @Param("id") String id, @Param("now") Instant now);

  record Waiting(
      String tenantId, String candidateId, String userId, String batchId, long version) {}

  java.util.List<Waiting> dueWaiting(@Param("now") Instant now);

  void waitingState(
      @Param("tenant") String tenant,
      @Param("candidate") String candidate,
      @Param("state") String state);

  void confirmationState(
      @Param("tenant") String tenant,
      @Param("candidate") String candidate,
      @Param("state") String state);
}

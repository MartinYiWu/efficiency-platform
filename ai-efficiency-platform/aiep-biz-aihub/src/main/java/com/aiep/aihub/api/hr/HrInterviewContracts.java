package com.aiep.aihub.api.hr;

import java.time.Instant;
import java.util.List;

/** 面试官和安全导出使用物理白名单DTO；此处不存在评分、等级、联系方式。 */
public final class HrInterviewContracts {
  private HrInterviewContracts() {}

  public record Template(
      String id,
      String departmentId,
      String name,
      String status,
      long version,
      List<String> layerInstructions,
      List<Integer> counts,
      List<Integer> durations,
      String round,
      String language) {}

  public record SaveTemplate(
      String departmentId,
      String name,
      long expectedVersion,
      List<String> layerInstructions,
      List<Integer> counts,
      List<Integer> durations,
      String round,
      String language) {}

  public record Reference(String excellent, String qualified, String needsVerification) {}

  public record Question(
      String id,
      int layer,
      String title,
      String purpose,
      List<String> answerPoints,
      List<String> followUps,
      Reference references,
      String sourceType,
      List<String> sourceIds,
      int minutes,
      String dimension) {}

  public record ResumeSection(String kind, String text) {}

  public record InterviewSet(
      String id,
      String candidateId,
      String positionId,
      long version,
      String status,
      int targetMinutes,
      int estimatedMinutes,
      List<Question> questions,
      List<Integer> insufficientLayers,
      Instant createdAt,
      List<ResumeSection> resumeSections) {
    public InterviewSet(
        String id,
        String candidateId,
        String positionId,
        long version,
        String status,
        int targetMinutes,
        int estimatedMinutes,
        List<Question> questions,
        List<Integer> insufficientLayers,
        Instant createdAt) {
      this(
          id,
          candidateId,
          positionId,
          version,
          status,
          targetMinutes,
          estimatedMinutes,
          questions,
          insufficientLayers,
          createdAt,
          List.of());
    }
  }

  public record GenerateRequest(
      String candidateId,
      String positionId,
      int targetMinutes,
      List<Integer> counts,
      List<Integer> durations,
      String templateId,
      String templateVersion,
      String round,
      String language,
      long expectedCandidateVersion) {}

  public record EditRequest(long expectedVersion, List<Question> questions) {}

  public record RegenerationRequest(long expectedVersion) {}

  public record AssignRequest(
      String setId, long setVersion, String interviewerId, Instant expiresAt) {}

  public record Assignment(
      String id,
      String setId,
      long setVersion,
      String interviewerId,
      Instant expiresAt,
      String status) {}

  public record InterviewGuide(
      String setId,
      long version,
      String positionName,
      List<Question> questions,
      String disclaimer,
      List<ResumeSection> resumeSections) {
    public InterviewGuide(
        String setId,
        long version,
        String positionName,
        List<Question> questions,
        String disclaimer) {
      this(setId, version, positionName, questions, disclaimer, List.of());
    }
  }

  public record ContactExportModel(InterviewGuide guide, HrTalentContracts.ContactView contact) {}

  public record ExportRequest(
      String setId, long setVersion, String format, String assignmentId, boolean includeContact) {}

  public record ExportView(
      String id,
      String status,
      String format,
      String grantId,
      Instant expiresAt,
      String failureCode) {}
}

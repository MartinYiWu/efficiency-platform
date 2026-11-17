package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrInterviewContracts.*;
import com.aiep.aihub.repository.hr.HrTalentMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 下载grant持久化10分钟一次，下载前复检指派及来源，不能跨角色复用。 */
@Service
public class HrInterviewExportService {
  private final HrContactService contacts;
  private final HrTalentMapper mapper;
  private final HrInterviewService interviews;
  private final HrInterviewAssignmentService assignments;
  private final HrSensitiveJsonCodec codec;
  private final ObjectMapper json;
  private final HrAuditService audit;
  private final HrTalentSearchService talent;

  public HrInterviewExportService(
      HrContactService contacts,
      HrTalentMapper mapper,
      HrInterviewService interviews,
      HrInterviewAssignmentService assignments,
      HrSensitiveJsonCodec codec,
      ObjectMapper json,
      HrAuditService audit,
      HrTalentSearchService talent) {
    this.contacts = contacts;
    this.mapper = mapper;
    this.interviews = interviews;
    this.assignments = assignments;
    this.codec = codec;
    this.json = json;
    this.audit = audit;
    this.talent = talent;
  }

  @Transactional
  public ExportView create(HrActor actor, ExportRequest request) {
    if (!Set.of("PDF", "WORD").contains(request.format())) throw HrTalentSearchService.invalid();
    if (request.includeContact() && request.assignmentId() != null)
      throw new HrBusinessException("HR_EXPORT_CONTACT_FORBIDDEN", "联系版不能供面试官链接使用", 403);
    InterviewGuide guide;
    if (request.assignmentId() != null) {
      guide = assignments.assigned(actor, request.assignmentId());
      if (!guide.setId().equals(request.setId()) || guide.version() != request.setVersion())
        throw HrTalentSearchService.missing();
    } else {
      HrAccessPolicy.require(actor, "hr:interview:export");
      var set = interviews.get(actor, request.setId(), request.setVersion());
      var permitted = talent.authorized(actor, set.candidateId(), "hr:candidate:read");
      HrAccessPolicy.requireFor(
          actor, "hr:interview:export", permitted.departmentId(), permitted.id(), "CANDIDATE");
      guide = assignments.preview(actor, set.id());
      if (guide.version() != request.setVersion()) throw HrCandidateMergeService.conflict();
    }
    Object model = guide;
    if (request.includeContact()) {
      var set = interviews.get(actor, request.setId(), request.setVersion());
      var grant =
          contacts.grant(
              actor,
              set.candidateId(),
              new com.aiep.aihub.api.hr.HrTalentContracts.ContactRequest("招聘负责人明确确认生成独立联系版"));
      model = new ContactExportModel(guide, contacts.read(actor, grant.id()));
    }
    Instant expires = Instant.now().plusSeconds(600);
    var row =
        new HrTalentMapper.ExportRow(
            UUID.randomUUID().toString(),
            actor.tenantId(),
            request.setId(),
            request.setVersion(),
            actor.userId(),
            request.assignmentId(),
            request.format() + (request.includeContact() ? "_CONTACT" : ""),
            codec.seal(write(model)),
            UUID.randomUUID().toString(),
            expires,
            "READY");
    mapper.insertExport(row);
    var candidate =
        mapper.candidate(
            actor.tenantId(),
            mapper.set(actor.tenantId(), request.setId(), request.setVersion()).candidateId());
    audit.append(actor, "INTERVIEW_EXPORTED", row.id(), candidate.departmentId());
    return view(row);
  }

  public ExportView get(HrActor actor, String id) {
    var row = mapper.export(actor.tenantId(), id);
    authorize(actor, row);
    return view(row);
  }

  @Transactional
  public byte[] download(HrActor actor, String grant) {
    var row = mapper.download(actor.tenantId(), grant);
    authorize(actor, row);
    if (mapper.consumeExport(actor.tenantId(), row.id(), Instant.now()) != 1)
      throw HrTalentSearchService.missing();
    try {
      if (row.format().endsWith("_CONTACT")) {
        ContactExportModel model =
            json.readValue(codec.open(row.payload()), ContactExportModel.class);
        return row.format().startsWith("PDF")
            ? HrInterviewDocumentRenderer.pdf(model)
            : HrInterviewDocumentRenderer.word(model);
      }
      InterviewGuide guide = json.readValue(codec.open(row.payload()), InterviewGuide.class);
      return row.format().equals("PDF")
          ? HrInterviewDocumentRenderer.pdf(guide)
          : HrInterviewDocumentRenderer.word(guide);
    } catch (HrBusinessException e) {
      throw e;
    } catch (Exception e) {
      throw new HrBusinessException("HR_EXPORT_RENDER_FAILED", "文件渲染失败", 503);
    }
  }

  public String format(HrActor actor, String grant) {
    var row = mapper.download(actor.tenantId(), grant);
    authorize(actor, row);
    return row.format().replace("_CONTACT", "");
  }

  private void authorize(HrActor actor, HrTalentMapper.ExportRow row) {
    if (row == null
        || !actor.userId().equals(row.userId())
        || !"READY".equals(row.status())
        || !row.expiresAt().isAfter(Instant.now())) throw HrTalentSearchService.missing();
    if (row.format().endsWith("_CONTACT")) {
      if (row.assignmentId() != null) throw HrTalentSearchService.missing();
      var set = interviews.get(actor, row.setId(), row.setVersion());
      talent.authorized(actor, set.candidateId(), "hr:candidate:contact");
    }
    if (row.assignmentId() != null) assignments.assigned(actor, row.assignmentId());
    else {
      HrAccessPolicy.require(actor, "hr:interview:export");
      var set = interviews.get(actor, row.setId(), row.setVersion());
      var c = talent.authorized(actor, set.candidateId(), "hr:candidate:read");
      HrAccessPolicy.requireFor(
          actor, "hr:interview:export", c.departmentId(), c.id(), "CANDIDATE");
    }
  }

  private ExportView view(HrTalentMapper.ExportRow row) {
    return new ExportView(
        row.id(),
        row.status(),
        row.format().replace("_CONTACT", ""),
        row.grantId(),
        row.expiresAt(),
        null);
  }

  private String write(Object value) {
    try {
      return json.writeValueAsString(value);
    } catch (Exception e) {
      throw new IllegalStateException("HR_EXPORT_ENCODING_FAILED");
    }
  }
}

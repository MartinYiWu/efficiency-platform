package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.repository.hr.HrExecutionMapper;
import com.aiep.platformfile.api.PrivateFileFacade;
import java.time.*;
import java.util.UUID;
import org.springframework.stereotype.Service;

/** 原件每次读取重新鉴权，单次十分钟授权不等于公开下载链接。 */
@Service
public class HrEvidenceService {
  public record Grant(String id, Instant expiresAt) {}

  public record Original(String filename, byte[] content) {}

  private final HrCandidateService candidates;
  private final HrExecutionMapper mapper;
  private final PrivateFileFacade files;
  private HrAuditService audit;

  @org.springframework.beans.factory.annotation.Autowired
  public HrEvidenceService(
      HrCandidateService candidates,
      HrExecutionMapper mapper,
      PrivateFileFacade files,
      HrAuditService audit) {
    this(candidates, mapper, files);
    this.audit = audit;
  }

  public HrEvidenceService(
      HrCandidateService candidates, HrExecutionMapper mapper, PrivateFileFacade files) {
    this.candidates = candidates;
    this.mapper = mapper;
    this.files = files;
  }

  public Grant grant(HrActor actor, String id) {
    var c = candidates.candidate(actor, id);
    HrAccessPolicy.requireFor(actor, "hr:candidate:original", c.departmentId(), id, "CANDIDATE");
    var source = mapper.sourceByCandidate(actor.tenantId(), id);
    if (source == null || source.fileId() == null) throw HrPositionService.missing();
    String grant = UUID.randomUUID().toString();
    Instant expires = Instant.now().plusSeconds(600);
    mapper.originalGrant(actor.tenantId(), id, actor.userId(), grant, expires);
    if (audit != null) audit.append(actor, "ORIGINAL_ACCESS_GRANTED", id, c.departmentId());
    return new Grant(grant, expires);
  }

  public Original read(HrActor actor, String id) {
    var grant = mapper.findOriginalGrant(actor.tenantId(), id);
    if (grant == null
        || !actor.userId().equals(grant.userId())
        || !grant.expiresAt().isAfter(Instant.now())) throw HrPositionService.missing();
    var c = candidates.candidate(actor, grant.candidateId());
    HrAccessPolicy.requireFor(
        actor, "hr:candidate:original", c.departmentId(), c.id(), "CANDIDATE");
    var source = mapper.sourceByCandidate(actor.tenantId(), c.id());
    if (source == null
        || source.fileId() == null
        || mapper.consumeOriginalGrant(actor.tenantId(), id, Instant.now()) != 1)
      throw HrPositionService.missing();
    return new Original(
        safeFilename(candidates.facts(actor, c.id()).filename()),
        files.read(actor.tenantId(), c.id(), source.fileId()));
  }

  private static String safeFilename(String value) {
    return value == null
        ? "resume.bin"
        : value.replaceAll("[\\r\\n\\u0000-\\u001F]", "_").replace('\\', '_').replace('/', '_');
  }
}

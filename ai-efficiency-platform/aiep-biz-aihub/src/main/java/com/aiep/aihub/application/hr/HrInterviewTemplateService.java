package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrInterviewContracts.*;
import com.aiep.aihub.repository.hr.HrSettingsRepository;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 六层面试模板独立版本化，已发布历史不覆盖；缓存冻结具体版本内容。 */
@Service
public class HrInterviewTemplateService {
  private static final String KIND = "INTERVIEW_TEMPLATE";
  private final HrSettingsRepository repository;

  public HrInterviewTemplateService(HrSettingsRepository repository) {
    this.repository = repository;
  }

  public List<Template> list(HrActor actor) {
    HrAccessPolicy.require(actor, "hr:config:read");
    return repository.list(actor, KIND, Template.class).stream()
        .filter(t -> permitted(actor, t))
        .toList();
  }

  private boolean permitted(HrActor actor, Template t) {
    try {
      HrAccessPolicy.requireFor(actor, "hr:config:read", t.departmentId(), null, "CONFIG");
      return true;
    } catch (HrBusinessException e) {
      return false;
    }
  }

  public Template get(HrActor actor, String id) {
    Template t = repository.get(actor, KIND, id, Template.class);
    HrAccessPolicy.requireFor(actor, "hr:config:read", t.departmentId(), null, "CONFIG");
    return t;
  }

  public Template published(HrActor actor, String id, String version) {
    var current = get(actor, id);
    if (version == null) throw HrTalentSearchService.invalid();
    return repository.versions(actor, KIND, id, Template.class).stream()
        .filter(t -> "PUBLISHED".equals(t.status()) && Long.toString(t.version()).equals(version))
        .findFirst()
        .orElseThrow(HrTalentSearchService::missing);
  }

  @Transactional
  public Template save(HrActor actor, String id, SaveTemplate request) {
    HrAccessPolicy.requireFor(actor, "hr:config:edit", request.departmentId(), null, "CONFIG");
    if (request.name() == null
        || request.name().isBlank()
        || request.name().length() > 80
        || request.layerInstructions() == null
        || request.layerInstructions().size() != 6
        || request.layerInstructions().stream().anyMatch(v -> v == null || v.length() > 1000)
        || request.counts() == null
        || request.durations() == null
        || request.round() == null
        || request.round().length() > 80
        || request.language() == null
        || request.language().length() > 30) throw HrTalentSearchService.invalid();
    HrInterviewRules.estimated(
        request.counts().stream().mapToInt(Integer::intValue).toArray(),
        request.durations().stream().mapToInt(Integer::intValue).toArray());
    if (id == null) {
      if (request.expectedVersion() != 0) throw HrTalentSearchService.invalid();
      id = UUID.randomUUID().toString();
    } else {
      var old = get(actor, id);
      if (old.version() != request.expectedVersion()
          || !old.departmentId().equals(request.departmentId()))
        throw HrCandidateMergeService.conflict();
    }
    var t =
        new Template(
            id,
            request.departmentId(),
            request.name(),
            "DRAFT",
            request.expectedVersion() + 1,
            List.copyOf(request.layerInstructions()),
            List.copyOf(request.counts()),
            List.copyOf(request.durations()),
            request.round(),
            request.language());
    repository.save(
        actor, KIND, id, t.departmentId(), request.expectedVersion(), t.version(), t, "SAVE_DRAFT");
    return t;
  }

  @Transactional
  public Template publish(HrActor actor, String id, long expected) {
    var old = get(actor, id);
    HrAccessPolicy.requireFor(actor, "hr:config:publish", old.departmentId(), null, "CONFIG");
    if (old.version() != expected) throw HrCandidateMergeService.conflict();
    var t =
        new Template(
            id,
            old.departmentId(),
            old.name(),
            "PUBLISHED",
            old.version() + 1,
            old.layerInstructions(),
            old.counts(),
            old.durations(),
            old.round(),
            old.language());
    repository.save(actor, KIND, id, t.departmentId(), old.version(), t.version(), t, "PUBLISH");
    return t;
  }

  public List<Template> versions(HrActor actor, String id) {
    get(actor, id);
    return repository.versions(actor, KIND, id, Template.class);
  }
}

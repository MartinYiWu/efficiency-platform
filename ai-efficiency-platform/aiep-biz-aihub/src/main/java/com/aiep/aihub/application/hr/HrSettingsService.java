package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrSettingsContracts.*;
import com.aiep.aihub.repository.hr.HrSettingsRepository;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 设置草稿与发布不可变，发布不更新历史岗位/授权。 */
@Service
public class HrSettingsService {
  private final HrSettingsRepository repository;
  private final com.aiep.aihub.repository.hr.HrBatchMapper batches;

  public HrSettingsService(
      HrSettingsRepository repository, com.aiep.aihub.repository.hr.HrBatchMapper batches) {
    this.repository = repository;
    this.batches = batches;
  }

  public static Settings defaults(String department) {
    return new Settings(
        department,
        "DEFAULT",
        12,
        3,
        3,
        30,
        80,
        65,
        50,
        "",
        20971520,
        104857600,
        100,
        0,
        HrProtectedAttributes.FIELDS);
  }

  public Settings get(HrActor actor, String department) {
    HrAccessPolicy.requireFor(actor, "hr:config:read", department, null, "CONFIG");
    return repository.exists(actor, "SETTINGS", department)
        ? repository.get(actor, "SETTINGS", department, Settings.class)
        : defaults(department);
  }

  public Settings published(HrActor actor, String department) {
    HrAccessPolicy.department(actor, department);
    if (!repository.exists(actor, "SETTINGS", department))
      throw new HrBusinessException("HR_SETTINGS_NOT_PUBLISHED", "尚未发布全局配置", 409);
    return repository
        .publicationHistory(
            actor, "SETTINGS", department, Settings.class, "hr:candidate:upload", "CANDIDATE")
        .stream()
        .filter(s -> "PUBLISHED".equals(s.status()))
        .findFirst()
        .orElseThrow(() -> new HrBusinessException("HR_SETTINGS_NOT_PUBLISHED", "尚未发布全局配置", 409));
  }

  @Transactional
  public Settings save(HrActor actor, SaveSettings input) {
    HrAccessPolicy.require(actor, "hr:config:edit");
    Settings old = get(actor, input.departmentId());
    if (old.version() != input.expectedVersion()) throw HrPositionService.conflict();
    Settings next =
        new Settings(
            input.departmentId(),
            "DRAFT",
            input.retentionMonths(),
            input.confirmationWaitDays(),
            input.maxModelAttempts(),
            input.failedItemRetentionDays(),
            input.highThreshold(),
            input.middleThreshold(),
            input.lowThreshold(),
            input.noticeVersion(),
            input.maxFileBytes(),
            input.maxArchiveBytes(),
            input.maxBatchItems(),
            old.version() + 1,
            defaults(input.departmentId()).prohibitedAttributes(),
            input.authorizationText());
    validate(next, old);
    repository.save(
        actor,
        "SETTINGS",
        input.departmentId(),
        input.departmentId(),
        old.version(),
        next.version(),
        next,
        "SAVE_DRAFT");
    return next;
  }

  @Transactional
  public Settings publish(HrActor actor, Publish input) {
    HrAccessPolicy.require(actor, "hr:config:publish");
    var old = get(actor, input.departmentId());
    if (old.version() != input.expectedVersion() || old.version() == 0)
      throw HrPositionService.conflict();
    if (old.noticeVersion() == null || old.noticeVersion().isBlank())
      throw HrPositionService.invalid("发布须配置告知文本版本");
    var next =
        new Settings(
            old.departmentId(),
            "PUBLISHED",
            old.retentionMonths(),
            old.confirmationWaitDays(),
            old.maxModelAttempts(),
            old.failedItemRetentionDays(),
            old.highThreshold(),
            old.middleThreshold(),
            old.lowThreshold(),
            old.noticeVersion(),
            old.maxFileBytes(),
            old.maxArchiveBytes(),
            old.maxBatchItems(),
            old.version() + 1,
            old.prohibitedAttributes(),
            old.authorizationText());
    HrAccessPolicy.require(actor, "hr:settings:edit");
    if (next.authorizationText() == null
        || next.authorizationText().strip().length() < 10
        || next.authorizationText().length() > 5000)
      throw HrPositionService.invalid("发布须配置10至5000字授权告知正文");
    var policy = batches.latestPolicy(actor.tenantId());
    long policyVersion = policy == null ? 0 : policy.version();
    var nextPolicy =
        new com.aiep.aihub.api.hr.HrBatchContracts.Policy(
            UUID.randomUUID().toString(),
            next.authorizationText().strip(),
            next.retentionMonths(),
            next.confirmationWaitDays(),
            next.maxModelAttempts(),
            next.failedItemRetentionDays(),
            next.highThreshold(),
            next.middleThreshold(),
            next.lowThreshold(),
            policyVersion + 1);
    batches.insertPolicy(
        new com.aiep.aihub.repository.hr.HrBatchMapper.PolicyRow(
            nextPolicy.id(),
            actor.tenantId(),
            repository.encode(nextPolicy),
            nextPolicy.version(),
            java.time.Instant.now()));
    repository.save(
        actor,
        "SETTINGS",
        old.departmentId(),
        old.departmentId(),
        old.version(),
        next.version(),
        next,
        "PUBLISH");
    return next;
  }

  public List<Settings> versions(HrActor actor, String department) {
    get(actor, department);
    return repository.versions(actor, "SETTINGS", department, Settings.class);
  }

  public List<Audit> audits(HrActor actor, String department) {
    if (department != null) HrAccessPolicy.department(actor, department);
    return repository.audits(actor).stream()
        .filter(a -> department == null || department.equals(a.departmentId()))
        .map(
            a ->
                new Audit(
                    a.id(),
                    a.departmentId(),
                    a.kind(),
                    a.objectId(),
                    a.action(),
                    a.actorId(),
                    a.version(),
                    a.at()))
        .toList();
  }

  public static void validate(Settings s, Settings old) {
    if (s.retentionMonths() < 1
        || s.retentionMonths() > 60
        || s.confirmationWaitDays() < 1
        || s.confirmationWaitDays() > 30
        || s.maxModelAttempts() < 1
        || s.maxModelAttempts() > 3
        || s.failedItemRetentionDays() < 1
        || s.failedItemRetentionDays() > 90
        || s.lowThreshold() < 0
        || s.highThreshold() > 100
        || s.highThreshold() <= s.middleThreshold()
        || s.middleThreshold() <= s.lowThreshold()) throw HrPositionService.invalid("全局默认值越界");
    if (s.maxFileBytes() < 1
        || s.maxArchiveBytes() < 1
        || s.maxBatchItems() < 1
        || s.maxFileBytes() > old.maxFileBytes()
        || s.maxArchiveBytes() > old.maxArchiveBytes()
        || s.maxBatchItems() > old.maxBatchItems()) throw HrPositionService.invalid("安全上限只能降低");
    if (s.authorizationText() != null && s.authorizationText().length() > 5000)
      throw HrPositionService.invalid("告知正文超过5000字");
    if (s.noticeVersion() != null && s.noticeVersion().length() > 100)
      throw HrPositionService.invalid("告知版本过长");
  }
}

package com.aiep.aihub.repository.hr;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.application.hr.*;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.*;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Repository;

/** 模板、词典、沙箱和设置共享不可变文档持久机制；不持久候选人正文。 */
@Repository
public class HrSettingsRepository {
  private final HrSettingsMapper mapper;
  private final ObjectMapper json;

  public HrSettingsRepository(HrSettingsMapper mapper, ObjectMapper json) {
    this.mapper = mapper;
    this.json = json;
  }

  public HrSettingsMapper.Row find(HrActor actor, String kind, String id) {
    var row = mapper.find(actor.tenantId(), kind, id);
    if (row == null) throw new HrBusinessException("HR_OBJECT_NOT_FOUND", "对象不存在或不可访问", 404);
    HrAccessPolicy.department(actor, row.departmentId());
    if (configKind(kind))
      HrAccessPolicy.requireFor(actor, "hr:config:read", row.departmentId(), null, "CONFIG");
    return row;
  }

  public <T> T get(HrActor actor, String kind, String id, Class<T> type) {
    return decode(find(actor, kind, id).payload(), type);
  }

  public <T> List<T> list(HrActor actor, String kind, Class<T> type) {
    var departments =
        configKind(kind)
            ? HrAccessPolicy.departmentsFor(actor, "hr:config:read")
            : actor.departmentIds();
    if (departments.isEmpty()) return List.of();
    return mapper.list(actor.tenantId(), kind, departments).stream()
        .map(r -> decode(r.payload(), type))
        .toList();
  }

  public <T> List<T> versions(HrActor actor, String kind, String id, Class<T> type) {
    find(actor, kind, id);
    return mapper.versions(actor.tenantId(), kind, id).stream()
        .map(r -> decode(r.payload(), type))
        .toList();
  }

  public List<String> candidateIds(HrActor actor, String department) {
    HrAccessPolicy.require(actor, "hr:candidate:read");
    HrAccessPolicy.department(actor, department);
    return mapper.candidateIds(actor.tenantId(), department, Instant.now());
  }

  public <T> List<T> publicationHistory(
      HrActor actor,
      String kind,
      String department,
      Class<T> type,
      String permission,
      String objectKind) {
    HrAccessPolicy.requireFor(actor, permission, department, null, objectKind);
    return mapper.versions(actor.tenantId(), kind, department).stream()
        .map(r -> decode(r.payload(), type))
        .toList();
  }

  public boolean exists(HrActor actor, String kind, String id) {
    return mapper.find(actor.tenantId(), kind, id) != null;
  }

  @org.springframework.transaction.annotation.Transactional
  public void save(
      HrActor actor,
      String kind,
      String id,
      String department,
      long expected,
      long version,
      Object value,
      String action) {
    HrAccessPolicy.department(actor, department);
    if (configKind(kind))
      HrAccessPolicy.requireFor(
          actor,
          "PUBLISH".equals(action) ? "hr:config:publish" : "hr:config:edit",
          department,
          null,
          "CONFIG");
    var row =
        new HrSettingsMapper.Row(actor.tenantId(), kind, id, department, encode(value), version);
    try {
      if (expected == 0) {
        if (version != 1) throw conflict();
        mapper.insert(row);
      } else if (mapper.update(row, expected) != 1) throw conflict();
    } catch (DuplicateKeyException e) {
      throw conflict();
    }
    mapper.append(
        actor.tenantId(),
        kind,
        id,
        new HrSettingsMapper.VersionRow(
            UUID.randomUUID().toString(), row.payload(), version, Instant.now()));
    mapper.audit(
        actor.tenantId(),
        new HrSettingsMapper.AuditRow(
            UUID.randomUUID().toString(),
            department,
            kind,
            id,
            action,
            actor.userId(),
            version,
            Instant.now()));
  }

  public List<HrSettingsMapper.AuditRow> audits(HrActor actor) {
    HrAccessPolicy.require(actor, "hr:config:read");
    var departments = HrAccessPolicy.departmentsFor(actor, "hr:config:read");
    return departments.isEmpty() ? List.of() : mapper.audits(actor.tenantId(), departments);
  }

  public String encode(Object value) {
    try {
      return json.writeValueAsString(value);
    } catch (JsonProcessingException e) {
      throw new IllegalStateException("HR_CONFIGURATION_ENCODING_FAILED");
    }
  }

  public <T> T decode(String text, Class<T> type) {
    try {
      return json.readValue(text, type);
    } catch (JsonProcessingException e) {
      throw new IllegalStateException("HR_CONFIGURATION_INVALID");
    }
  }

  private static boolean configKind(String kind) {
    return Set.of("TEMPLATE", "DICTIONARY", "DICTIONARY_IMPORT", "SETTINGS", "INTERVIEW_TEMPLATE")
        .contains(kind);
  }

  private static HrBusinessException conflict() {
    return new HrBusinessException("HR_VERSION_CONFLICT", "版本已更新，请重新加载", 409);
  }
}

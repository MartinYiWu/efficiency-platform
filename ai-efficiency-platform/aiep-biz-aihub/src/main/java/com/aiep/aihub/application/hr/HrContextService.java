package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrPositionContracts.*;
import com.aiep.aihub.repository.hr.HrExecutionMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import org.springframework.stereotype.Service;

/** 上下文按内容冻结，与评分配置分开；历史JD不得用当前岗位正文替代。 */
@Service
public class HrContextService {
  public record Context(
      String positionId,
      String name,
      String departmentId,
      String level,
      String jdText,
      String version) {}

  private final HrExecutionMapper mapper;
  private final ObjectMapper json;

  public HrContextService(HrExecutionMapper mapper, ObjectMapper json) {
    this.mapper = mapper;
    this.json = json;
  }

  public String freeze(HrActor actor, Draft draft) {
    String hash =
        HrPositionService.hash(
            java.util.Arrays.asList(
                draft.name(), draft.departmentId(), draft.level(), draft.jdText()));
    String version = "ctx-" + hash.substring(0, 32);
    Context c =
        new Context(
            draft.positionId(),
            draft.name(),
            draft.departmentId(),
            draft.level(),
            draft.jdText(),
            version);
    try {
      mapper.insertContext(
          actor.tenantId(),
          draft.positionId(),
          version,
          json.writeValueAsString(c),
          hash,
          actor.userId(),
          Instant.now());
    } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
      throw new IllegalStateException("HR_CONTEXT_ENCODING_FAILED");
    }
    return version;
  }

  public Context get(HrActor actor, String position, String version) {
    HrAccessPolicy.position(actor, position);
    String value = mapper.getContext(actor.tenantId(), position, version);
    if (value == null) throw HrPositionService.missing();
    try {
      Context c = json.readValue(value, Context.class);
      HrAccessPolicy.department(actor, c.departmentId());
      return c;
    } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
      throw new IllegalStateException("HR_CONTEXT_ENCODING_FAILED");
    }
  }
}

package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.repository.hr.HrExecutionMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;

/** 新批次冻结当前安全上限，之后调整全局值不追溯已创建对象。 */
@Service
public class HrBatchLimits {
  public record Limits(
      long maxFileBytes, long maxArchiveBytes, int maxBatchItems, int maxAttempts) {}

  private final HrExecutionMapper mapper;
  private final HrSettingsService settings;
  private final ObjectMapper json;

  public HrBatchLimits(HrExecutionMapper mapper, HrSettingsService settings, ObjectMapper json) {
    this.mapper = mapper;
    this.settings = settings;
    this.json = json;
  }

  public Limits freeze(HrActor actor, String department, String batch) {
    var s = settings.published(actor, department);
    var l =
        new Limits(s.maxFileBytes(), s.maxArchiveBytes(), s.maxBatchItems(), s.maxModelAttempts());
    try {
      mapper.insertLimits(actor.tenantId(), batch, json.writeValueAsString(l));
      return l;
    } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
      throw new IllegalStateException("HR_LIMIT_ENCODING_FAILED");
    }
  }

  public Limits get(HrActor actor, String batch) {
    String value = mapper.getLimits(actor.tenantId(), batch);
    if (value == null)
      throw new HrBusinessException("HR_BATCH_LIMITS_REQUIRED", "批次缺冻结安全配置，请创建新批次", 409);
    try {
      return json.readValue(value, Limits.class);
    } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
      throw new IllegalStateException("HR_LIMIT_ENCODING_FAILED");
    }
  }
}

package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.fasterxml.jackson.databind.*;
import org.springframework.stereotype.Service;

@Service
public class HrReadinessService implements HrInterviewBindingPort {
  private final HrSemanticGateway gateway;
  private final ObjectMapper json;

  public HrReadinessService(HrSemanticGateway gateway, ObjectMapper json) {
    this.gateway = gateway;
    this.json = json;
  }

  public JsonNode inspect(HrActor actor) {
    return gateway.execute(actor, 6108, "hr-readiness", json.createObjectNode());
  }

  public void requireModels(HrActor actor) {
    if (!inspect(actor).path("published_assets").asBoolean())
      throw new HrBusinessException(
          "HR_CONFIG_PUBLISHED_ASSETS_NOT_READY", "请先发布并绑定人事Prompt、模型和价格策略", 503);
  }

  public java.util.Map<String, com.aiep.aihub.api.hr.HrPositionContracts.AssetBinding> bindings(
      HrActor actor) {
    JsonNode all = inspect(actor);
    if (!all.path("published_assets").asBoolean())
      throw new HrBusinessException("HR_CONFIG_PUBLISHED_ASSETS_NOT_READY", "人事已发布资产未就绪", 503);
    return json.convertValue(
        all.path("bindings"),
        json.getTypeFactory()
            .constructMapType(
                java.util.Map.class,
                String.class,
                com.aiep.aihub.api.hr.HrPositionContracts.AssetBinding.class));
  }

  @Override
  public Binding resolve(HrActor actor) {
    JsonNode all = inspect(actor);
    if (!all.path("published_assets").asBoolean())
      throw new HrBusinessException(
          "HR_CONFIG_PUBLISHED_ASSETS_NOT_READY", "人事Prompt与模型绑定未就绪", 503);
    JsonNode binding = all.path("bindings").path("hr.interview.generate");
    String prompt =
        binding.path("prompt_version").asText() + ":" + binding.path("prompt_hash").asText();
    String route =
        binding.path("model_route_version").asText()
            + ":"
            + binding.path("model_route").asText()
            + ":"
            + binding.path("output_schema_hash").asText();
    return new Binding(prompt, route);
  }
}

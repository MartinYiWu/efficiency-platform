package com.aiep.platformai.api.dto;

import static com.aiep.platformai.api.dto.MemoryDeriveRequest.*;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import java.io.IOException;
import java.util.List;
import java.util.Set;

/** Agent 返回的未提交候选；所有状态仍须业务层复核与CAS。 */
@JsonDeserialize(using=MemoryDeriveResponse.Deserializer.class)
public record MemoryDeriveResponse(
    @JsonProperty("contract_version") String contractVersion, String skill,
    @JsonProperty("plan_id") String planId,
    @JsonProperty("plan_fingerprint") String planFingerprint,
    @JsonProperty("runtime_id") String runtimeId,
    @JsonProperty("run_id") String runId,
    @JsonProperty("operation_id") String operationId,
    @JsonProperty("execution_scope") MemoryRuntimeManifest.Scope executionScope,
    MemoryDeriveRequest.Assets assets,
    @JsonProperty("baseline_ref") String baselineRef,
    JsonNode candidate, JsonNode validation, JsonNode benefit) {
  public MemoryDeriveResponse {
    if(!"memory-derive-result/1".equals(contractVersion)||!"memory.derive".equals(skill)) invalid();
    for(String value:new String[]{planId,runtimeId,runId,operationId,baselineRef}) id(value);
    digest(planFingerprint); if(executionScope==null||assets==null) invalid();
    fields(candidate,"mode","summary","proposals");
    String mode=text(candidate,"mode");if(!Set.of("SUMMARY","PROPOSALS","BOTH").contains(mode))invalid();
    array(candidate.path("proposals"),0,"SUMMARY".equals(mode)?0:16);
    candidate.path("proposals").forEach(MemoryDeriveResponse::proposal);
    if("PROPOSALS".equals(mode)){if(!candidate.path("summary").isNull())invalid();}else summary(candidate.path("summary"));rejectCommitted(candidate);
    if("SUMMARY".equals(mode))fields(validation,"free_text_quality","commit_status","session_revision","source_revision","source_watermark","frozen_critical_digest","source_dependencies","expires_at");
    else {
      fields(validation,"free_text_quality","commit_status","session_revision","source_revision","source_watermark","frozen_critical_digest","source_dependencies","expires_at","proposals_validated");
      array(validation.path("proposals_validated"),0,16);
      for(var value:validation.path("proposals_validated")){
        fields(value,"kind","field_key","value","decision_status","index_status","source_dependencies");
        proposalFields(value);
        if(!"PROPOSED".equals(text(value,"decision_status"))||!"NOT_REQUESTED".equals(text(value,"index_status")))invalid();
        dependencies(value.path("source_dependencies"),1,512);
      }
    }
    if(!"UNVERIFIED".equals(text(validation,"free_text_quality"))||!"NOT_COMMITTED".equals(text(validation,"commit_status"))) invalid();
    number(validation,"session_revision"); number(validation,"source_revision"); number(validation,"expires_at");
    digest(text(validation,"frozen_critical_digest")); dependencies(validation.path("source_dependencies"),1,512);
    if("PROPOSALS".equals(mode)){if(!validation.path("source_watermark").isNull())invalid();}else watermark(validation.path("source_watermark"));
    fields(benefit,"status","reason","T_before","T_after","commit_status");
    if(!("PROPOSALS".equals(mode)?Set.of("NOT_REQUESTED"):Set.of("BENEFICIAL","REJECTED")).contains(text(benefit,"status"))||!"NOT_COMMITTED".equals(text(benefit,"commit_status"))) invalid();
    id(text(benefit,"reason"));
    for(String name:List.of("T_before","T_after")) if(!benefit.path(name).isNull()) number(benefit,name);
    if("BENEFICIAL".equals(text(benefit,"status"))&&(benefit.path("T_before").isNull()||benefit.path("T_after").isNull()||number(benefit,"T_after")>=number(benefit,"T_before"))) invalid();
    candidate=candidate.deepCopy(); validation=validation.deepCopy(); benefit=benefit.deepCopy();
  }
  @Override public JsonNode candidate() { return candidate.deepCopy(); }
  @Override public JsonNode validation() { return validation.deepCopy(); }
  @Override public JsonNode benefit() { return benefit.deepCopy(); }
  @Override public String toString() { return "MemoryDeriveResponse[redacted]"; }
  public void validateBinding(MemoryDeriveRequest request) {
    if(!planId.equals(request.planId())||!planFingerprint.equals(request.planFingerprint())
        ||!runtimeId.equals(request.runtimeId())||!runId.equals(request.runId())||!operationId.equals(request.operationId())
        ||!executionScope.equals(request.executionScope())||!assets.equals(request.assets())||!baselineRef.equals(request.baselineRef())
        ||!candidate.path("mode").asText().equals(request.mode())
        ||number(validation,"session_revision")!=request.sessionRevision()||number(validation,"source_revision")!=request.sourceRevision()
        ||(!"PROPOSALS".equals(request.mode())&&(!scope(candidate.path("summary").path("scope")).equals(request.executionScope().conversation())
        ||!candidate.path("summary").path("watermark").equals(validation.path("source_watermark"))
        ||number(validation.path("source_watermark"),"source_revision")!=request.sourceRevision())))
      throw new IllegalArgumentException("DERIVE_BINDING_CONFLICT");
  }
  private static void proposal(JsonNode value){fields(value,"kind","field_key","value");proposalFields(value);}
  private static void proposalFields(JsonNode value){
    if(!"PREFERENCE".equals(text(value,"kind"))||!Set.of("response.language","response.detail_level","response.format").contains(text(value,"field_key")))invalid();
    String proposed=text(value,"value");if(proposed.isBlank()||proposed.getBytes(java.nio.charset.StandardCharsets.UTF_8).length+128>512)invalid();
  }
  private static void watermark(JsonNode node) {
    fields(node,"source_revision","first_sequence","last_sequence");
    number(node,"source_revision"); if(number(node,"first_sequence")>number(node,"last_sequence")) invalid();
  }
  private static void summary(JsonNode node) {
    fields(node,"segment_id","scope","covered_sources","watermark","goal","confirmed_constraints","decisions","rejected_options","open_questions","important_refs","uncertainties","source_dependencies","expires_at");
    id(text(node,"segment_id")); scope(node.path("scope")); dependencies(node.path("covered_sources"),1,128);
    watermark(node.path("watermark")); entry(node.path("goal"));
    for(String name:List.of("confirmed_constraints","decisions","rejected_options","open_questions","important_refs","uncertainties")) {
      array(node.path(name),0,128); node.path(name).forEach(MemoryDeriveRequest::entry);
    }
    dependencies(node.path("source_dependencies"),0,512); number(node,"expires_at");
  }
  private static void rejectCommitted(JsonNode node) {
    if(node.isObject()) node.fields().forEachRemaining(field->{
      if(Set.of("commit_status","status","state").contains(field.getKey())&&"COMMITTED".equals(field.getValue().asText())) invalid();
      rejectCommitted(field.getValue());
    });
    else if(node.isArray()) node.forEach(MemoryDeriveResponse::rejectCommitted);
  }
  public static final class Deserializer extends JsonDeserializer<MemoryDeriveResponse> {
    @Override public MemoryDeriveResponse deserialize(JsonParser parser,DeserializationContext context) throws IOException {
      parser.enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);
      JsonNode node=parser.getCodec().readTree(parser);
      fields(node,"contract_version","skill","plan_id","plan_fingerprint","runtime_id","run_id","operation_id","execution_scope","assets","baseline_ref","candidate","validation","benefit");
      return new MemoryDeriveResponse(text(node,"contract_version"),text(node,"skill"),text(node,"plan_id"),text(node,"plan_fingerprint"),text(node,"runtime_id"),text(node,"run_id"),text(node,"operation_id"),execution(node.path("execution_scope")),MemoryDeriveRequest.assets(node.path("assets")),text(node,"baseline_ref"),node.path("candidate"),node.path("validation"),node.path("benefit"));
    }
  }
}

package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;
import java.util.Set;

/** 原执行的不可扩权摘要计划；正文仅用于内部传输，不进入诊断字符串。 */
@JsonDeserialize(using = MemoryDeriveRequest.Deserializer.class)
public record MemoryDeriveRequest(
    @JsonProperty("contract_version") String contractVersion,
    @JsonProperty("plan_id") String planId,
    @JsonProperty("plan_fingerprint") String planFingerprint,
    @JsonProperty("runtime_id") String runtimeId,
    @JsonProperty("runtime_kind") String runtimeKind,
    @JsonProperty("run_id") String runId,
    @JsonProperty("operation_id") String operationId,
    @JsonProperty("authorization_ref") String authorizationRef,
    @JsonProperty("budget_id") String budgetId,
    @JsonProperty("deadline_epoch_seconds") Long deadlineEpochSeconds,
    @JsonProperty("execution_scope") MemoryRuntimeManifest.Scope executionScope,
    String mode,
    @JsonProperty("baseline_ref") String baselineRef,
    Assets assets,
    List<FrozenSource> sources,
    JsonNode events,
    @JsonProperty("required_entries") JsonNode requiredEntries,
    @JsonProperty("session_revision") Long sessionRevision,
    @JsonProperty("source_revision") Long sourceRevision,
    @JsonProperty("authority_ref") String authorityRef) {
  private static final ObjectMapper JSON = new ObjectMapper();
  public MemoryDeriveRequest {
    if (!"memory-derive/1".equals(contractVersion) || !Set.of("SUMMARY","PROPOSALS","BOTH").contains(mode)) invalid();
    for (String id : new String[]{planId,runtimeId,runId,operationId,authorizationRef,budgetId,baselineRef,authorityRef}) id(id);
    digest(planFingerprint);
    if (deadlineEpochSeconds == null || deadlineEpochSeconds <= 0 || sessionRevision == null
        || sessionRevision < 0 || sourceRevision == null || sourceRevision < 0 || assets == null) invalid();
    if (executionScope == null || executionScope.conversation() == null) invalid();
    var scope = executionScope.conversation();
    String domain = switch (runtimeKind == null ? "" : runtimeKind) {
      case "OPERATIONS" -> "operations"; case "CUSTOMER_SERVICE" -> "customer-service";
      default -> throw new IllegalArgumentException("DERIVE_SCOPE_MISMATCH");
    };
    if (!domain.equals(scope.domain()) || !"CONVERSATION".equals(scope.sessionKind())) invalid();
    for (String identity : new String[]{executionScope.taskId(),executionScope.executionId(),executionScope.subtaskId(),executionScope.purpose(),executionScope.executionAgentId()}) id(identity);
    if (sources == null || sources.isEmpty() || sources.size() > 128) invalid();
    sources = List.copyOf(sources);
    for (var source : sources) {
      if (!JSON.valueToTree(scope).equals(source.metadata().path("scope"))) invalid();
    }
    array(events,0,897); events = events.deepCopy(); events.forEach(MemoryDeriveRequest::event);
    array(requiredEntries,"PROPOSALS".equals(mode)?0:1,897); requiredEntries = requiredEntries.deepCopy(); requiredEntries.forEach(MemoryDeriveRequest::entry);
  }
  public record Assets(
      @JsonProperty("memory_policy_version") String memoryPolicyVersion,
      @JsonProperty("window_policy_version") String windowPolicyVersion,
      @JsonProperty("model_ref") String modelRef,
      @JsonProperty("prompt_ref") String promptRef,
      @JsonProperty("schema_ref") String schemaRef) {
    public Assets { for (String value : new String[]{memoryPolicyVersion,windowPolicyVersion,modelRef,promptRef,schemaRef}) id(value); }
  }
  public record FrozenSource(JsonNode metadata, String body, @JsonProperty("body_sha256") String bodySha256) {
    public FrozenSource {
      source(metadata); metadata = metadata.deepCopy(); digest(bodySha256);
      if (body == null || body.codePointCount(0,body.length()) > 20000 || invalidUnicode(body) || !sha256(body).equals(bodySha256))
        throw new IllegalArgumentException("DERIVE_SOURCE_BODY_MISMATCH");
    }
    @Override public JsonNode metadata() { return metadata.deepCopy(); }
    @Override public String toString() { return "FrozenSource[redacted]"; }
  }
  @Override public JsonNode events() { return events.deepCopy(); }
  @Override public JsonNode requiredEntries() { return requiredEntries.deepCopy(); }
  @Override public String toString() { return "MemoryDeriveRequest[redacted]"; }
  public String canonicalFingerprint() {
    ObjectNode tree = JSON.valueToTree(this); tree.remove("plan_fingerprint");
    tree.path("sources").forEach(source -> ((ObjectNode)source).remove("body"));
    for (int i=0;i<sources.size();i++) {
      var allowed=((ObjectNode)tree.path("sources").get(i).path("metadata")).putArray("allowed_purposes");
      var values=new java.util.ArrayList<String>(); sources.get(i).metadata().path("allowed_purposes").forEach(n->values.add(n.textValue()));
      values.stream().distinct().sorted().forEach(allowed::add);
    }
    return MemoryPacketDigest.canonicalDigest(tree);
  }
  public void validateBinding(String tenantId) {
    if (!executionScope.conversation().tenantId().equals(tenantId) || !canonicalFingerprint().equals(planFingerprint))
      throw new IllegalArgumentException("DERIVE_BINDING_CONFLICT");
  }
  public static String sha256(String value) {
    try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))); }
    catch (java.security.NoSuchAlgorithmException error) { throw new IllegalStateException("DERIVE_DIGEST_UNAVAILABLE"); }
  }
  static void invalid() { throw new IllegalArgumentException("MEMORY_DERIVE_CONTRACT_INVALID"); }
  private static boolean invalidUnicode(String value) { return value.codePoints().anyMatch(cp->cp>=0xd800&&cp<=0xdfff); }
  static void id(String value) { if(value==null||value.isBlank()||value.codePointCount(0,value.length())>128||invalidUnicode(value)) invalid(); }
  static void digest(String value) { if(value==null||!value.matches("[0-9a-f]{64}")) invalid(); }
  static void fields(JsonNode node,String... names) {
    if(node==null||!node.isObject()||node.size()!=names.length) invalid();
    for(String name:names) if(!node.has(name)) invalid();
  }
  static String text(JsonNode node,String name) { JsonNode value=node.get(name); if(value==null||!value.isTextual()) invalid(); return value.textValue(); }
  static long number(JsonNode node,String name) { JsonNode value=node.get(name); if(value==null||!value.isIntegralNumber()||!value.canConvertToLong()||value.longValue()<0) invalid(); return value.longValue(); }
  static void array(JsonNode node,int min,int max) { if(node==null||!node.isArray()||node.size()<min||node.size()>max) invalid(); }
  static void dependency(JsonNode node) {
    fields(node,"source_type","source_id","source_version","grant_epoch","source_epoch","deletion_epoch");
    for(String name:List.of("source_type","source_id","source_version")) id(text(node,name));
    for(String name:List.of("grant_epoch","source_epoch","deletion_epoch")) number(node,name);
  }
  static void dependencies(JsonNode node,int min,int max) { array(node,min,max); node.forEach(MemoryDeriveRequest::dependency); }
  private static void critical(JsonNode values) {
    array(values,0,128);
    for(var value:values) {
      fields(value,"field_ref","kind","value","timezone"); id(text(value,"field_ref")); bounded(text(value,"value"));
      String kind=text(value,"kind"); if(!Set.of("NUMBER","DATE","CONSTRAINT").contains(kind)) invalid();
      if("DATE".equals(kind)) { try { java.time.ZoneId.of(text(value,"timezone")); } catch(Exception error) { invalid(); } }
      else if(!value.path("timezone").isNull()) invalid();
    }
  }
  private static void bounded(String value) { if(value==null||value.isBlank()||value.codePointCount(0,value.length())>2048||invalidUnicode(value)) invalid(); }
  private static void identity(JsonNode node) {
    id(text(node,"claim_ref"));
    if(!Set.of("USER_REQUIREMENT","BUSINESS_FACT","MODEL_SUGGESTION","UNCONFIRMED_INFERENCE").contains(text(node,"content_origin"))
        || !Set.of("PROPOSED","CONFIRMED","REJECTED","UNRESOLVED").contains(text(node,"decision_status"))) invalid();
    critical(node.path("critical_values"));
  }
  static void entry(JsonNode node) {
    if(node.has("reason")) fields(node,"claim_ref","text","content_origin","decision_status","source_refs","basis_event_ref","critical_values","reason");
    else fields(node,"claim_ref","text","content_origin","decision_status","source_refs","basis_event_ref","critical_values");
    identity(node); bounded(text(node,"text")); dependencies(node.path("source_refs"),1,128);
    if(!node.path("basis_event_ref").isNull()) dependency(node.path("basis_event_ref"));
    if(node.has("reason")&&!node.path("reason").isNull()) bounded(text(node,"reason"));
  }
  static void event(JsonNode node) {
    fields(node,"event_ref","claim_ref","authority","content_origin","decision_status","critical_values","rejection_reason");
    identity(node); dependency(node.path("event_ref"));
    if(!Set.of("USER","JAVA","MODEL").contains(text(node,"authority"))) invalid();
    if(!node.path("rejection_reason").isNull()) bounded(text(node,"rejection_reason"));
  }
  private static void source(JsonNode node) {
    fields(node,"source_ref","scope","sequence","group_id","group_members","source_dependencies","completed","source_kind","allowed_purposes","summary_scope_ref","proposals_scope_ref","summary_retention_ref","proposals_retention_ref","expires_at","critical_values");
    dependency(node.path("source_ref")); number(node,"sequence"); number(node,"expires_at"); id(text(node,"group_id"));
    dependencies(node.path("group_members"),1,128); dependencies(node.path("source_dependencies"),1,512);
    if(!node.path("completed").isBoolean()||!Set.of("ORIGINAL","SUMMARY").contains(text(node,"source_kind"))) invalid();
    array(node.path("allowed_purposes"),0,2);
    node.path("allowed_purposes").forEach(p->{if(!p.isTextual()||!Set.of("SUMMARY","PROPOSALS").contains(p.textValue())) invalid();});
    for(String name:List.of("summary_scope_ref","proposals_scope_ref","summary_retention_ref","proposals_retention_ref")) if(!node.path(name).isNull()) id(text(node,name));
    critical(node.path("critical_values")); scope(node.path("scope"));
  }
  static MemoryContextEnvelope.Scope scope(JsonNode node) {
    fields(node,"tenant_id","user_id","domain","top_level_agent_id","session_kind","session_id");
    return new MemoryContextEnvelope.Scope(text(node,"tenant_id"),text(node,"user_id"),text(node,"domain"),text(node,"top_level_agent_id"),text(node,"session_kind"),node.path("session_id").isNull()?null:text(node,"session_id"));
  }
  static MemoryRuntimeManifest.Scope execution(JsonNode node) {
    fields(node,"conversation","task_id","execution_id","subtask_id","purpose","execution_agent_id");
    return new MemoryRuntimeManifest.Scope(scope(node.path("conversation")),text(node,"task_id"),text(node,"execution_id"),text(node,"subtask_id"),text(node,"purpose"),text(node,"execution_agent_id"));
  }
  static Assets assets(JsonNode node) {
    fields(node,"memory_policy_version","window_policy_version","model_ref","prompt_ref","schema_ref");
    return new Assets(text(node,"memory_policy_version"),text(node,"window_policy_version"),text(node,"model_ref"),text(node,"prompt_ref"),text(node,"schema_ref"));
  }
  public static final class Deserializer extends JsonDeserializer<MemoryDeriveRequest> {
    @Override public MemoryDeriveRequest deserialize(JsonParser parser,DeserializationContext context) throws IOException {
      parser.enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);
      JsonNode node=parser.getCodec().readTree(parser);
      fields(node,"contract_version","plan_id","plan_fingerprint","runtime_id","runtime_kind","run_id","operation_id","authorization_ref","budget_id","deadline_epoch_seconds","execution_scope","mode","baseline_ref","assets","sources","events","required_entries","session_revision","source_revision","authority_ref");
      array(node.path("sources"),1,128); var sources=new java.util.ArrayList<FrozenSource>();
      for(var source:node.path("sources")) { fields(source,"metadata","body","body_sha256"); sources.add(new FrozenSource(source.path("metadata"),text(source,"body"),text(source,"body_sha256"))); }
      return new MemoryDeriveRequest(text(node,"contract_version"),text(node,"plan_id"),text(node,"plan_fingerprint"),text(node,"runtime_id"),text(node,"runtime_kind"),text(node,"run_id"),text(node,"operation_id"),text(node,"authorization_ref"),text(node,"budget_id"),number(node,"deadline_epoch_seconds"),execution(node.path("execution_scope")),text(node,"mode"),text(node,"baseline_ref"),assets(node.path("assets")),sources,node.path("events"),node.path("required_entries"),number(node,"session_revision"),number(node,"source_revision"),text(node,"authority_ref"));
    }
  }
}

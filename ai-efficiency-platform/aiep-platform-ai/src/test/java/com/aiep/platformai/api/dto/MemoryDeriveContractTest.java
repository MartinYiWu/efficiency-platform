package com.aiep.platformai.api.dto;

import static org.junit.jupiter.api.Assertions.*;
import com.aiep.platformai.agent.AgentClientProperties;
import com.aiep.platformai.agent.AgentTransportException;
import com.aiep.platformai.agent.HttpAgentClient;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

class MemoryDeriveContractTest {
  private final ObjectMapper json = new ObjectMapper().disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
  private static final String GOLDEN = """
      {
        "contract_version":"memory-derive/1","plan_id":"plan-中文😀","plan_fingerprint":"0000000000000000000000000000000000000000000000000000000000000000",
        "runtime_id":"runtime","runtime_kind":"OPERATIONS","run_id":"run","operation_id":"operation",
        "authorization_ref":"parent","budget_id":"original-budget","deadline_epoch_seconds":4102444800,
        "execution_scope":{"conversation":{"tenant_id":"tenant-中文😀","user_id":"user-A","domain":"operations","top_level_agent_id":"operations","session_kind":"CONVERSATION","session_id":"session"},"task_id":"task","execution_id":"execution","subtask_id":"node","purpose":"ANSWER","execution_agent_id":"operations"},
        "mode":"SUMMARY","baseline_ref":"baseline/1","assets":{"memory_policy_version":"memory/2","window_policy_version":"window/7","model_ref":"model/1","prompt_ref":"prompt/1","schema_ref":"schema/1"},
        "sources":[{"metadata":{"source_ref":{"source_type":"MESSAGE","source_id":"message","source_version":"v1","grant_epoch":0,"source_epoch":1,"deletion_epoch":0},"scope":{"tenant_id":"tenant-中文😀","user_id":"user-A","domain":"operations","top_level_agent_id":"operations","session_kind":"CONVERSATION","session_id":"session"},"sequence":1,"group_id":"group","group_members":[{"source_type":"MESSAGE","source_id":"message","source_version":"v1","grant_epoch":0,"source_epoch":1,"deletion_epoch":0}],"source_dependencies":[{"source_type":"MESSAGE","source_id":"message","source_version":"v1","grant_epoch":0,"source_epoch":1,"deletion_epoch":0}],"completed":true,"source_kind":"ORIGINAL","allowed_purposes":["SUMMARY","PROPOSALS"],"summary_scope_ref":"summary-scope","proposals_scope_ref":"proposal-scope","summary_retention_ref":"retention/1","proposals_retention_ref":"retention/1","expires_at":4102444800,"critical_values":[]},"body":"合成原文😀","body_sha256":"BODY_DIGEST"}],
        "events":[],"required_entries":[{"claim_ref":"goal","text":"合成目标","content_origin":"MODEL_SUGGESTION","decision_status":"PROPOSED","source_refs":[{"source_type":"MESSAGE","source_id":"message","source_version":"v1","grant_epoch":0,"source_epoch":1,"deletion_epoch":0}],"basis_event_ref":null,"critical_values":[]}],
        "session_revision":7,"source_revision":4,"authority_ref":"authority/1"
      }
      """;
  private ObjectNode fixture() throws Exception {
    return (ObjectNode)json.readTree(GOLDEN.replace("BODY_DIGEST",MemoryDeriveRequest.sha256("合成原文😀")));
  }
  private MemoryDeriveRequest request() throws Exception {
    var node=fixture(); var first=json.treeToValue(node,MemoryDeriveRequest.class);
    node.put("plan_fingerprint",first.canonicalFingerprint()); return json.treeToValue(node,MemoryDeriveRequest.class);
  }
  private ObjectNode response(MemoryDeriveRequest request) throws Exception {
    ObjectNode result=json.createObjectNode(); result.put("contract_version","memory-derive-result/1"); result.put("skill","memory.derive");
    JsonNode input=json.valueToTree(request);
    for(String field:new String[]{"plan_id","plan_fingerprint","runtime_id","run_id","operation_id","execution_scope","assets","baseline_ref"}) result.set(field,input.path(field));
    var candidate=result.putObject("candidate"); candidate.put("mode","SUMMARY"); candidate.putArray("proposals");
    var summary=candidate.putObject("summary"); summary.put("segment_id","segment"); summary.set("scope",input.path("execution_scope").path("conversation"));
    summary.putArray("covered_sources").add(input.path("sources").get(0).path("metadata").path("source_ref"));
    var watermark=summary.putObject("watermark"); watermark.put("source_revision",4); watermark.put("first_sequence",1); watermark.put("last_sequence",1);
    summary.set("goal",input.path("required_entries").get(0));
    for(String name:new String[]{"confirmed_constraints","decisions","rejected_options","open_questions","important_refs","uncertainties"}) summary.putArray(name);
    summary.set("source_dependencies",summary.path("covered_sources")); summary.put("expires_at",4102444700L);
    var validation=result.putObject("validation"); validation.put("free_text_quality","UNVERIFIED"); validation.put("commit_status","NOT_COMMITTED");
    validation.put("session_revision",7); validation.put("source_revision",4); validation.set("source_watermark",watermark.deepCopy());
    validation.put("frozen_critical_digest","c".repeat(64)); validation.set("source_dependencies",summary.path("covered_sources")); validation.put("expires_at",4102444700L);
    var benefit=result.putObject("benefit"); benefit.put("status","BENEFICIAL"); benefit.put("reason","SUMMARY_BENEFIT_VERIFIED"); benefit.put("T_before",200); benefit.put("T_after",100); benefit.put("commit_status","NOT_COMMITTED");
    return result;
  }
  @Test void goldenMatchesPythonUtf8CanonicalDigestAndRedactsBody() throws Exception {
    var request=request(); assertEquals("ed26d378bda7c23bd3ba6173786690bbdf0a8d58b59154a742206da558dce455",request.canonicalFingerprint());
    var expected=fixture(); expected.put("plan_fingerprint",request.planFingerprint());
    assertEquals(expected,json.readTree(json.writeValueAsString(request)));
    request.validateBinding("tenant-中文😀");
    assertThrows(IllegalArgumentException.class,()->request.validateBinding("tenant-other"));
    assertFalse(request.toString().contains("合成")); assertFalse(request.sources().get(0).toString().contains("合成"));
    var exposed=request.sources().get(0).metadata(); ((ObjectNode)exposed).put("sequence",999);
    assertEquals(1,request.sources().get(0).metadata().path("sequence").asInt());
  }
  @Test void rejectsMissingEpochCoercionUnknownBudgetAndChangedBody() throws Exception {
    for(String field:new String[]{"deadline_epoch_seconds","session_revision","source_revision"}) {
      for(JsonNode bad:new JsonNode[]{json.getNodeFactory().booleanNode(true),json.getNodeFactory().textNode("1"),json.getNodeFactory().numberNode(1.0)}) {
        var raw=fixture(); raw.set(field,bad); assertThrows(Exception.class,()->json.treeToValue(raw,MemoryDeriveRequest.class));
      }
      var missing=fixture(); missing.remove(field); assertThrows(Exception.class,()->json.treeToValue(missing,MemoryDeriveRequest.class));
    }
    var epoch=fixture(); ((ObjectNode)epoch.path("sources").get(0).path("metadata").path("source_ref")).remove("source_epoch");
    assertThrows(Exception.class,()->json.treeToValue(epoch,MemoryDeriveRequest.class));
    var body=fixture(); ((ObjectNode)body.path("sources").get(0)).put("body","changed"); assertThrows(Exception.class,()->json.treeToValue(body,MemoryDeriveRequest.class));
    var budget=fixture(); budget.put("max_cost_cny",1000); assertThrows(Exception.class,()->json.treeToValue(budget,MemoryDeriveRequest.class));
    var mode=fixture(); mode.put("mode","OTHER"); assertThrows(Exception.class,()->json.treeToValue(mode,MemoryDeriveRequest.class));
  }
  @Test void proposalModesRequirePendingValidatedClosureAndSingleOriginalBinding()throws Exception{
    for(String mode:java.util.List.of("PROPOSALS","BOTH")){
      var raw=fixture();raw.put("mode",mode);var initial=json.treeToValue(raw,MemoryDeriveRequest.class);raw.put("plan_fingerprint",initial.canonicalFingerprint());
      var request=json.treeToValue(raw,MemoryDeriveRequest.class);var result=response(request);
      var candidate=result.withObject("/candidate");candidate.put("mode",mode);
      var proposal=candidate.withArray("/proposals").addObject();proposal.put("kind","PREFERENCE");proposal.put("field_key","response.language");proposal.put("value","zh-CN");
      var validation=result.withObject("/validation");var checked=validation.putArray("proposals_validated").addObject();checked.setAll(proposal);
      checked.put("decision_status","PROPOSED");checked.put("index_status","NOT_REQUESTED");checked.set("source_dependencies",validation.path("source_dependencies").deepCopy());
      if(mode.equals("PROPOSALS")){
        candidate.putNull("summary");validation.putNull("source_watermark");
        var benefit=result.withObject("/benefit");benefit.put("status","NOT_REQUESTED");benefit.put("reason","DERIVE_PROPOSALS_ONLY");benefit.putNull("T_before");benefit.putNull("T_after");
      }
      json.treeToValue(result,MemoryDeriveResponse.class).validateBinding(request);
      checked.put("decision_status","CONFIRMED");assertThrows(Exception.class,()->json.treeToValue(result,MemoryDeriveResponse.class));
    }
  }
  @Test void acceptsOnlyOriginalBindingAndUncommittedUnverifiedResult() throws Exception {
    var request=request(); var raw=response(request); var parsed=json.treeToValue(raw,MemoryDeriveResponse.class); parsed.validateBinding(request);
    for(String field:new String[]{"plan_id","runtime_id","run_id","operation_id","baseline_ref"}) {
      var changed=raw.deepCopy(); changed.put(field,"other"); var result=json.treeToValue(changed,MemoryDeriveResponse.class);
      assertThrows(IllegalArgumentException.class,()->result.validateBinding(request));
    }
    var committed=raw.deepCopy(); committed.withObject("/validation").put("commit_status","COMMITTED"); assertThrows(Exception.class,()->json.treeToValue(committed,MemoryDeriveResponse.class));
    var quality=raw.deepCopy(); quality.withObject("/validation").put("free_text_quality","VERIFIED"); assertThrows(Exception.class,()->json.treeToValue(quality,MemoryDeriveResponse.class));
    var mismatch=raw.deepCopy(); mismatch.withObject("/assets").put("model_ref","other"); var result=json.treeToValue(mismatch,MemoryDeriveResponse.class); assertThrows(IllegalArgumentException.class,()->result.validateBinding(request));
    var extra=raw.deepCopy(); extra.put("authorized",true); assertThrows(Exception.class,()->json.treeToValue(extra,MemoryDeriveResponse.class));
  }
  @Test void usesExistingSkillAuthAndNeverRetries402() throws Exception {
    var calls=new AtomicInteger(); var properties=new AgentClientProperties(); properties.setInternalSecret("s".repeat(32));
    var builder=WebClient.builder().exchangeFunction(http->{
      calls.incrementAndGet(); assertEquals("/skill/execute",http.url().getPath());
      assertEquals("tenant-中文😀",http.headers().getFirst("X-Tenant-ID"));
      assertEquals("Bearer "+"s".repeat(32),http.headers().getFirst("Authorization"));
      return Mono.just(ClientResponse.create(HttpStatus.PAYMENT_REQUIRED).header("Content-Type","application/json").body("{\"code\":\"PAID_PAYMENT_REQUIRED\"}").build());
    });
    var client=new HttpAgentClient(properties,builder,json); var request=request();
    var error=assertThrows(AgentTransportException.class,()->client.deriveMemory("tenant-中文😀",request));
    assertEquals(402,error.getStatusCode()); assertEquals("PAID_PAYMENT_REQUIRED",error.getErrorCode()); assertEquals(1,calls.get());
  }
  @Test void queryAndFinishOnlyOriginalRegisteredPlanAndStrictReceipt() throws Exception {
    var calls=new AtomicInteger(); var properties=new AgentClientProperties(); properties.setInternalSecret("s".repeat(32));
    var request=request(); var responseBody=new java.util.concurrent.atomic.AtomicReference<>(json.writeValueAsString(request));
    var builder=WebClient.builder().exchangeFunction(http->{
      calls.incrementAndGet();
      assertEquals("tenant-中文😀",http.headers().getFirst("X-Tenant-ID"));
      assertEquals("Bearer "+"s".repeat(32),http.headers().getFirst("Authorization"));
      assertTrue(http.url().getPath().equals("/internal/v1/memory/executions/execution/derive-plan")
          ||http.url().getPath().equals("/internal/v1/memory/executions/execution/derive-finish"));
      return Mono.just(ClientResponse.create(HttpStatus.OK).header("Content-Type","application/json").body(responseBody.get()).build());
    });
    var client=new HttpAgentClient(properties,builder,json);
    assertEquals(request,client.queryMemoryDerivePlan("tenant-中文😀","execution"));
    var changed=(ObjectNode)json.valueToTree(request); changed.put("plan_fingerprint","f".repeat(64));
    responseBody.set(json.writeValueAsString(changed));
    assertEquals("MEMORY_DERIVE_PLAN_INVALID",assertThrows(AgentTransportException.class,()->client.queryMemoryDerivePlan("tenant-中文😀","execution")).getErrorCode());
    changed=(ObjectNode)json.valueToTree(request); changed.withObject("/execution_scope").put("execution_id","other");
    responseBody.set(json.writeValueAsString(changed));
    assertThrows(AgentTransportException.class,()->client.queryMemoryDerivePlan("tenant-中文😀","execution"));
    responseBody.set("{\"code\":\"MEMORY_DERIVE_FINISHED\"}");
    client.finishMemoryDerive("tenant-中文😀","execution",request.planId(),request.planFingerprint(),"COMMITTED");
    client.finishMemoryDerive("tenant-中文😀","execution",request.planId(),request.planFingerprint(),"REJECTED");
    int before=calls.get();
    assertThrows(AgentTransportException.class,()->client.finishMemoryDerive("tenant-中文😀","execution",request.planId(),request.planFingerprint(),"PENDING"));
    assertEquals(before,calls.get());
    responseBody.set("{\"code\":\"MEMORY_DERIVE_FINISHED\",\"authorized\":true}");
    assertEquals("MEMORY_DERIVE_FINISH_INVALID",assertThrows(AgentTransportException.class,()->client.finishMemoryDerive("tenant-中文😀","execution",request.planId(),request.planFingerprint(),"REJECTED")).getErrorCode());
    assertEquals(before+1,calls.get());
  }
}

package com.aiep.aihub.memory;
import com.aiep.platformai.api.dto.*;
import com.aiep.aihub.application.memory.ConversationScopeResolver;
import com.aiep.aihub.application.operation.OperationActor;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;
class MemoryTransportContractTest {
 private final ObjectMapper json=new ObjectMapper();
 @Test void scopeTransportUsesSnakeCaseAndExplicitDisabledEmptyPacket() throws Exception {
  var resolver=new ConversationScopeResolver();
  var scope=resolver.conversation(new OperationActor("t","u"),"operations","s","t","u","operations");
  var envelope=resolver.envelope(scope);
  var request=new OperationAgentMessageRequest("hello","req","u",List.of(),"t",envelope);
  var tree=json.readTree(json.writeValueAsString(request));
  var memory=tree.get("memory_context");
  assertEquals("memory-context/1",memory.get("schema_version").asText());
  assertEquals("DISABLED",memory.get("memory_mode").asText()); assertTrue(memory.get("packet").isNull());
  assertEquals(6,memory.get("scope").size()); assertEquals("operations",memory.at("/scope/top_level_agent_id").asText());
  assertEquals("s",memory.at("/scope/session_id").asText()); assertFalse(memory.get("scope").has("tenantId"));
 }
 @Test void legacyConstructorsAndAbsentEnvelopeStayDisabled() throws Exception {
  var op=new OperationAgentMessageRequest("hello","r","u","t");
  assertEquals("DISABLED",op.memoryContext().memoryMode());assertNull(op.memoryContext().scope());
  var cs=new CustomerServiceRunRequest("customer-service-run/1","r","s","t","u","release","hello",List.of());
  assertEquals("DISABLED",cs.memoryContext().memoryMode());assertNull(cs.memoryContext().scope());
  var raw=json.readTree(json.writeValueAsString(cs)); ((com.fasterxml.jackson.databind.node.ObjectNode)raw).remove("memory_context");
  var decoded=json.treeToValue(raw,CustomerServiceRunRequest.class);
  assertEquals("DISABLED",decoded.memoryContext().memoryMode());assertNull(decoded.memoryContext().scope());
 }
 @Test void taskOnlyMapsNullSessionAndDoesNotInventPacket() {
  var resolver=new ConversationScopeResolver();var scope=resolver.taskOnly(new OperationActor("t","u"),"hr");
  assertNull(resolver.envelope(scope).scope().sessionId());assertNull(resolver.envelope(scope).packet());
 }
}

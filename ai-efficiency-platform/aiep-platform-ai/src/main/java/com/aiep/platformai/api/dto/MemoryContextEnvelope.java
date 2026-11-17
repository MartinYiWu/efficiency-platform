package com.aiep.platformai.api.dto;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
/** 中立认证信封；旧请求明确禁用，启用必须携带完整原执行授权。 */
public record MemoryContextEnvelope(
 @JsonProperty("schema_version") String schemaVersion,
 @JsonProperty("memory_mode") String memoryMode, Scope scope, MemoryContextPacket packet,
 @com.fasterxml.jackson.annotation.JsonInclude(com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL)
 MemoryAuthorization authorization) {
 public MemoryContextEnvelope(String schemaVersion,String memoryMode,Scope scope,MemoryContextPacket packet) {
  this(schemaVersion,memoryMode,scope,packet,null);
 }
 public MemoryContextEnvelope {
  if(!"memory-context/1".equals(schemaVersion)||!List.of("DISABLED","EXACT_ONLY").contains(memoryMode))throw new IllegalArgumentException("MEMORY_ENVELOPE_INVALID");
  if("DISABLED".equals(memoryMode)&&(packet!=null||authorization!=null))throw new IllegalArgumentException("MEMORY_DISABLED_ENVELOPE_INVALID");
  if("EXACT_ONLY".equals(memoryMode)&&(scope==null||packet==null||authorization==null
    ||!scope.equals(packet.scope())||!packet.policyVersion().equals(authorization.policy().version())
    ||packet.expiresAt()>authorization.deadlineEpochSeconds()
    ||authorization.inputDependencies().isEmpty()||!packet.safetyDependencies().containsAll(authorization.inputDependencies())
    ||!MemoryPacketDigest.digest(packet).equals(authorization.packetDigest())
    ||!MemoryPacketDigest.semanticDigest(packet).equals(authorization.semanticSnapshotDigest())))throw new IllegalArgumentException("MEMORY_ENVELOPE_BINDING_INVALID");
 }
 public static MemoryContextEnvelope disabled(){return new MemoryContextEnvelope("memory-context/1","DISABLED",null,null);}
 public record Scope(@JsonProperty("tenant_id") String tenantId,@JsonProperty("user_id") String userId,
  String domain,@JsonProperty("top_level_agent_id") String topLevelAgentId,
  @JsonProperty("session_kind") String sessionKind,@JsonProperty("session_id") String sessionId) {
  public Scope {
   for(String id:new String[]{tenantId,userId,domain,topLevelAgentId})requireIdentity(id);
   if(!List.of("operations","customer-service","hr").contains(domain)||!domain.equals(topLevelAgentId))throw new IllegalArgumentException("MEMORY_AGENT_SCOPE_INVALID");
   if("CONVERSATION".equals(sessionKind)){requireIdentity(sessionId);}
   else if(!"TASK_ONLY".equals(sessionKind)||sessionId!=null)throw new IllegalArgumentException("MEMORY_SESSION_INVALID");
  }
  private static void requireIdentity(String id) {
   if(id==null||id.isBlank()||id.codePointCount(0,id.length())>128
    ||id.codePoints().anyMatch(cp->cp>=0xd800&&cp<=0xdfff)
    ||id.getBytes(java.nio.charset.StandardCharsets.UTF_8).length>512)throw new IllegalArgumentException("MEMORY_SCOPE_INVALID");
  }
 }
}

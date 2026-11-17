package com.aiep.aihub.api.memory;
import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import java.util.Set;
/** 服务端归属；TASK_ONLY没有历史键，执行分支不能替代顶层Agent。 */
public record MemoryScopeDTO(
 @JsonProperty("tenant_id") String tenantId, @JsonProperty("user_id") String userId,
 String domain, @JsonProperty("top_level_agent_id") String topLevelAgentId,
 @JsonProperty("session_kind") String sessionKind, @JsonProperty("session_id") String sessionId) {
 public MemoryScopeDTO {
  requireId(tenantId);requireId(userId);
  if (!Set.of("operations","customer-service","hr").contains(domain) || !domain.equals(topLevelAgentId))
   throw new IllegalArgumentException("MEMORY_AGENT_SCOPE_INVALID");
  if ("CONVERSATION".equals(sessionKind) && !"hr".equals(domain)) requireId(sessionId);
  else if (!"TASK_ONLY".equals(sessionKind) || sessionId != null) throw new IllegalArgumentException("MEMORY_SESSION_SCOPE_INVALID");
 }
 @JsonIgnore public List<String> historyKey() {
  return "TASK_ONLY".equals(sessionKind) ? null : List.of(tenantId,userId,domain,topLevelAgentId,sessionId);
 }
 private static void requireId(String value) {
  if(value==null||value.isBlank()||value.codePointCount(0,value.length())>128
   ||value.codePoints().anyMatch(cp->cp>=0xd800&&cp<=0xdfff)
   ||value.getBytes(java.nio.charset.StandardCharsets.UTF_8).length>512)throw new IllegalArgumentException("MEMORY_SCOPE_ID_INVALID");
 }
}

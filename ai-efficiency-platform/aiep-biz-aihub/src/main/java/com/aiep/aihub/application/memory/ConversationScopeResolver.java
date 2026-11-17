package com.aiep.aihub.application.memory;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.application.operation.OperationActor;
import com.aiep.platformai.api.dto.MemoryContextEnvelope;
import org.springframework.stereotype.Component;
/** 只能接收服务端查询出的拥有关系，不接收浏览器scope。 */
@Component
public class ConversationScopeResolver {
 public MemoryScopeDTO conversation(OperationActor actor,String topAgent,String sessionId,
   String ownerTenant,String ownerUser,String ownerAgent) {
  if(!java.util.Set.of("operations","customer-service").contains(topAgent)
   ||!actor.tenantId().equals(ownerTenant)||!actor.userId().equals(ownerUser)||!topAgent.equals(ownerAgent))
   throw new IllegalArgumentException("MEMORY_CONVERSATION_NOT_OWNED");
  return new MemoryScopeDTO(actor.tenantId(),actor.userId(),topAgent,topAgent,"CONVERSATION",sessionId);
 }
 public MemoryScopeDTO taskOnly(OperationActor actor,String topAgent) {
  if(!java.util.Set.of("operations","customer-service","hr").contains(topAgent))throw new IllegalArgumentException("MEMORY_SESSION_SCOPE_INVALID");
  return new MemoryScopeDTO(actor.tenantId(),actor.userId(),topAgent,topAgent,"TASK_ONLY",null);
 }
 public MemoryContextEnvelope envelope(MemoryScopeDTO scope) {
  return new MemoryContextEnvelope("memory-context/1","DISABLED",
   new MemoryContextEnvelope.Scope(scope.tenantId(),scope.userId(),scope.domain(),scope.topLevelAgentId(),scope.sessionKind(),scope.sessionId()),null);
 }
}

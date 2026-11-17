package com.aiep.aihub.application.memory;
import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.repository.memory.MemoryMapper;
import com.aiep.aihub.repository.memory.MemoryPacketMapper;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Set;
import org.springframework.stereotype.Service;

/** 原登录及原执行范围复验；恢复幂等、三次刷新上限与绝对截止归原Agent持久门禁。 */
@Service
public class MemoryContextResumeService {
 private final MemoryScopePolicy scopes;private final MemorySessionBindingService bindings;private final MemoryPacketMapper packets;private final AiInvokeFacade ai;
 public MemoryContextResumeService(MemoryScopePolicy scopes,MemorySessionBindingService bindings,MemoryPacketMapper packets,AiInvokeFacade ai){this.scopes=scopes;this.bindings=bindings;this.packets=packets;this.ai=ai;}
 public MemoryResumeReceipt resume(IdentityFacade.Subject actor,MemoryScopeDTO scope,String executionId,MemoryResumeRequest request){
  scopes.require(actor,scope,Set.of());bindings.require(actor,scope);
  if(request==null||request.newContent()||request.mode()==null||!Set.of("cpu","refresh","paid").contains(request.mode())||request.operationHash()==null||!request.operationHash().matches("[0-9a-f]{64}"))throw new MemoryException("MEMORY_REQUEST_INVALID");
  MemoryMapper.identity(request.waitEventId());MemoryMapper.identity(request.resumeRequestId());
  var original=packets.findPacket(MemoryMapper.identity(scope.tenantId()),MemoryMapper.identity(executionId));
  if(original==null||original.packetRevision()!=request.packetRevision()||original.executionRevision()!=request.expectedExecutionRevision())throw new MemoryException("MEMORY_REVISION_CONFLICT");
  try{var json=new ObjectMapper();if(!json.readTree(original.scopeJson()).equals(json.valueToTree(scope)))throw new MemoryException("MEMORY_SCOPE_DENIED");}
  catch(java.io.IOException invalid){throw new MemoryException("MEMORY_STORAGE_UNAVAILABLE");}
  return ai.resumeMemoryExecution(scope.tenantId(),executionId,request);
 }
}

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
 private final MemoryPacketService authority;
 private final MemoryScopePolicy scopes;private final MemorySessionBindingService bindings;private final MemoryPacketMapper packets;private final AiInvokeFacade ai;
 public MemoryContextResumeService(MemoryScopePolicy scopes,MemorySessionBindingService bindings,MemoryPacketMapper packets,AiInvokeFacade ai){this(scopes,bindings,packets,ai,null);}
 @org.springframework.beans.factory.annotation.Autowired
 public MemoryContextResumeService(MemoryScopePolicy scopes,MemorySessionBindingService bindings,MemoryPacketMapper packets,AiInvokeFacade ai,MemoryPacketService authority){this.scopes=scopes;this.bindings=bindings;this.packets=packets;this.ai=ai;this.authority=authority;}
 /** 缺原Java run关联的runtime不能授权刷新；保留旧签名仅用于明确拒绝。 */
 public MemoryResumeReceipt onWait(String tenantId,String executionId,String eventRef,String resumeRequestId) {
  throw new MemoryException("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED");
 }
 /** 事件入口只接受原wait引用；候选ID由本地持久终态与目标版本统一选择。 */
 public MemoryResumeReceipt onWaitEvent(String tenantId,String executionId,String expectedRuntimeId,String eventRef) {
  return onWaitInternal(tenantId,executionId,expectedRuntimeId,eventRef,null);
 }
 /** expectedRuntimeId必须来自Java持久run→agentRun关联；显式ID保留受信兼容，事件不得自行选择。 */
 public MemoryResumeReceipt onWait(String tenantId,String executionId,String expectedRuntimeId,String eventRef,String resumeRequestId) {
  MemoryMapper.identity(resumeRequestId);
  return onWaitInternal(tenantId,executionId,expectedRuntimeId,eventRef,resumeRequestId);
 }
 private MemoryResumeReceipt onWaitInternal(String tenantId,String executionId,String expectedRuntimeId,String eventRef,String resumeRequestId) {
  if(authority==null||!authority.refreshEnabled())throw new MemoryException("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED");
  if(org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive())throw new MemoryException("MEMORY_REFRESH_TRANSACTION_INVALID");
  MemoryMapper.identity(expectedRuntimeId);MemoryMapper.identity(eventRef);
  var scope=authority.issuedScope(tenantId,executionId);
  var wait=ai.queryMemoryWait(tenantId,executionId,eventRef);
  if(wait==null||!expectedRuntimeId.equals(wait.runtimeId())||!eventRef.equals(wait.waitEventId())||!executionId.equals(wait.executionId())||!tenantId.equals(wait.scope().tenantId()))throw new MemoryException("MEMORY_RESUME_CONFLICT");
  var request=resumeRequestId==null?authority.prepareRefreshForWait(scope,wait):authority.prepareRefresh(scope,wait,resumeRequestId);
  var receipt=ai.resumeMemoryExecution(tenantId,executionId,request);
  return authority.recordReceipt(tenantId,executionId,request,receipt);
 }
 public MemoryResumeReceipt resume(IdentityFacade.Subject actor,MemoryScopeDTO scope,String executionId,MemoryResumeRequest request){
  scopes.require(actor,scope,Set.of());bindings.require(actor,scope);
  if(request==null||request.newContent()||request.mode()==null||!Set.of("cpu","refresh","paid").contains(request.mode())||request.operationHash()==null||!request.operationHash().matches("[0-9a-f]{64}"))throw new MemoryException("MEMORY_REQUEST_INVALID");
  if(request.isV2())throw new MemoryException("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED");
  MemoryMapper.identity(request.waitEventId());MemoryMapper.identity(request.resumeRequestId());
  var original=packets.findPacket(MemoryMapper.identity(scope.tenantId()),MemoryMapper.identity(executionId));
  if(original==null||original.packetRevision()!=request.packetRevision()||original.executionRevision()!=request.expectedExecutionRevision())throw new MemoryException("MEMORY_REVISION_CONFLICT");
  try{var json=new ObjectMapper();if(!json.readTree(original.scopeJson()).equals(json.valueToTree(scope)))throw new MemoryException("MEMORY_SCOPE_DENIED");}
  catch(java.io.IOException invalid){throw new MemoryException("MEMORY_STORAGE_UNAVAILABLE");}
  return ai.resumeMemoryExecution(scope.tenantId(),executionId,request);
 }
}

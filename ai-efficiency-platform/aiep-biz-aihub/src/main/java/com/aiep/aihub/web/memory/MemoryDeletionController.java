package com.aiep.aihub.web.memory;

import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.application.memory.*;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformcore.api.ApiResponse;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.Set;
import org.springframework.web.bind.annotation.*;

/** 忘记与明确重授权的安全HTTP投影；不接受客户端tenant/owner/登录引用或清理回执。 */
@RestController
@RequestMapping("/api/aihub")
public class MemoryDeletionController {
 private final MemoryScopePolicy scopes;private final MemoryForgetService forget;private final MemorySuppressionService suppressions;
 public MemoryDeletionController(MemoryScopePolicy scopes,MemoryForgetService forget,MemorySuppressionService suppressions){this.scopes=scopes;this.forget=forget;this.suppressions=suppressions;}
 @PostMapping("/memory-deletions") public ApiResponse<MemoryForgetService.JobResponse> forget(@RequestBody JsonNode body){
  fields(body,Set.of("topAgent","sessionId","itemId","expectedRevision","idempotencyKey","mode"));var actor=scopes.currentActor();String mode=string(body,"mode",false);
  return success(forget.forget(actor,new MemoryForgetService.ForgetCommand(scope(actor,body),string(body,"itemId",true),number(body,"expectedRevision"),string(body,"idempotencyKey",true),mode==null?"FORGET_AND_SUPPRESS":mode)));
 }
 @GetMapping("/memory-deletions/{id}") public ApiResponse<MemoryForgetService.JobResponse> get(@PathVariable String id,@RequestParam String topAgent,@RequestParam(required=false) String sessionId){var actor=scopes.currentActor();return success(forget.get(actor,scope(actor,topAgent,sessionId),id));}
 @PostMapping("/memory-suppressions/{id}/reauthorizations") public ApiResponse<MemoryController.PreferenceResponse> reauthorize(@PathVariable String id,@RequestBody JsonNode body){
  fields(body,Set.of("topAgent","sessionId","itemId","fieldKey","value","expectedRevision","expected_suppression_revision","idempotencyKey","confirmation"));var actor=scopes.currentActor();
  var result=suppressions.reauthorize(actor,id,new MemorySuppressionService.ReauthorizationCommand(scope(actor,body),string(body,"itemId",true),string(body,"fieldKey",true),string(body,"value",true),number(body,"expectedRevision"),number(body,"expected_suppression_revision"),string(body,"idempotencyKey",true),string(body,"confirmation",true)));
  return success(MemoryController.PreferenceResponse.of(result));
 }
 private MemoryScopeDTO scope(IdentityFacade.Subject actor,JsonNode body){return scope(actor,string(body,"topAgent",true),string(body,"sessionId",false));}
 private MemoryScopeDTO scope(IdentityFacade.Subject actor,String agent,String session){return new MemoryScopeDTO(actor.tenantId(),actor.userId(),agent,agent,session==null?"TASK_ONLY":"CONVERSATION",session);}
 private void fields(JsonNode body,Set<String> allowed){if(body==null||!body.isObject())throw new MemoryException("MEMORY_REQUEST_INVALID");var names=body.fieldNames();while(names.hasNext())if(!allowed.contains(names.next()))throw new MemoryException("MEMORY_REQUEST_INVALID");}
 private String string(JsonNode body,String key,boolean required){var value=body.get(key);if((value==null||value.isNull())&&!required)return null;if(value==null||!value.isTextual()||value.textValue().isBlank())throw new MemoryException("MEMORY_REQUEST_INVALID");return value.textValue();}
 private long number(JsonNode body,String key){var value=body.path(key);if(!value.isIntegralNumber()||!value.canConvertToLong()||value.longValue()<0)throw new MemoryException("MEMORY_REQUEST_INVALID");return value.longValue();}
 private <T> ApiResponse<T> success(T value){return ApiResponse.success(value).withTraceId(MemoryExceptionHandler.trace());}
}

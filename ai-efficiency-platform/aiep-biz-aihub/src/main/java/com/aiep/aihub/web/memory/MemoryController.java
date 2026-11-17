package com.aiep.aihub.web.memory;

import com.aiep.aihub.api.memory.*;
import com.aiep.aihub.api.memory.MemoryContracts.*;
import com.aiep.aihub.application.memory.MemoryScopePolicy;
import com.aiep.aihub.application.memory.MemoryPreferenceService;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformcore.api.ApiResponse;
import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.*;
import org.springframework.web.bind.annotation.*;

/** HTTP仅接受业务会话ID；tenant/user由认证主体构造，登录引用绝不进入响应。 */
@RestController
@RequestMapping("/api/aihub/memories")
public class MemoryController {
 private final MemoryFacade facade;private final MemoryScopePolicy policy;private final MemoryPreferenceService preferences;
 public MemoryController(MemoryFacade facade,MemoryScopePolicy policy,MemoryPreferenceService preferences){this.facade=facade;this.policy=policy;this.preferences=preferences;}
 @GetMapping public ApiResponse<PageResponse> list(@RequestParam String topAgent,@RequestParam(required=false) String sessionId,@RequestParam(defaultValue="1") int page,@RequestParam(defaultValue="20") int pageSize){
  if(page<1||page>1000000||pageSize<1||pageSize>100)throw new MemoryException("MEMORY_REQUEST_INVALID");
  var actor=policy.currentActor();var all=facade.listPreferences(actor,scope(actor,topAgent,sessionId),Set.of());
  int from=Math.min(all.size(),(page-1)*pageSize),to=Math.min(all.size(),from+pageSize);
  return success(new PageResponse(all.subList(from,to).stream().map(PreferenceResponse::of).toList(),all.size(),page,pageSize));
 }
 @GetMapping("/{id}") public ApiResponse<DetailResponse> get(@PathVariable String id,@RequestParam String topAgent,@RequestParam(required=false) String sessionId){
  var actor=policy.currentActor();var found=preferences.get(actor,scope(actor,topAgent,sessionId),id);
  return success(new DetailResponse(PreferenceResponse.of(found.preference()),found.history().stream().map(VersionResponse::of).toList()));
 }
 @PostMapping public ApiResponse<PreferenceResponse> save(@RequestBody JsonNode body){var request=parse(body,false);var actor=policy.currentActor();return success(PreferenceResponse.of(facade.savePreference(actor,command(actor,request))));}
 @PostMapping("/{id}/corrections") public ApiResponse<PreferenceResponse> correct(@PathVariable String id,@RequestBody JsonNode body){var request=parse(body,false);var actor=policy.currentActor();return success(PreferenceResponse.of(facade.correctPreference(actor,id,command(actor,request))));}
 @PostMapping("/{id}/decisions") public ApiResponse<PreferenceResponse> decide(@PathVariable String id,@RequestBody JsonNode body){
  if(body.has("proposalId")||body.has("proposal"))throw new MemoryException("FEATURE_DISABLED");
  var request=parse(body,true);var actor=policy.currentActor();return success(PreferenceResponse.of(preferences.decide(actor,id,command(actor,request),request.action())));
 }
 private PreferenceCommand command(IdentityFacade.Subject actor,PreferenceRequest request){return new PreferenceCommand(scope(actor,request.topAgent(),request.sessionId()),request.fieldKey(),request.value(),request.expectedRevision(),request.idempotencyKey(),null);}
 private MemoryScopeDTO scope(IdentityFacade.Subject actor,String agent,String session){return new MemoryScopeDTO(actor.tenantId(),actor.userId(),agent,agent,session==null?"TASK_ONLY":"CONVERSATION",session);}
 private PreferenceRequest parse(JsonNode body,boolean decision){
  Set<String> allowed=decision?Set.of("topAgent","sessionId","fieldKey","value","expectedRevision","idempotencyKey","action"):Set.of("topAgent","sessionId","fieldKey","value","expectedRevision","idempotencyKey");
  if(!body.isObject())throw new MemoryException("MEMORY_REQUEST_INVALID");
  var names=body.fieldNames();while(names.hasNext())if(!allowed.contains(names.next()))throw new MemoryException("MEMORY_REQUEST_INVALID");
  var revision=body.path("expectedRevision");if(!revision.isIntegralNumber()||!revision.canConvertToLong()||revision.longValue()<0)throw new MemoryException("MEMORY_REQUEST_INVALID");
  return new PreferenceRequest(string(body,"topAgent",true),string(body,"sessionId",false),string(body,"fieldKey",true),string(body,"value",true),revision.longValue(),string(body,"idempotencyKey",true),string(body,"action",decision));
 }
 private String string(JsonNode body,String key,boolean required){var value=body.get(key);if((value==null||value.isNull())&&!required)return null;if(value==null||!value.isTextual()||value.textValue().isBlank())throw new MemoryException("MEMORY_REQUEST_INVALID");return value.textValue();}
 private <T> ApiResponse<T> success(T data){return ApiResponse.success(data).withTraceId(MemoryExceptionHandler.trace());}
 private record PreferenceRequest(String topAgent,String sessionId,String fieldKey,String value,long expectedRevision,String idempotencyKey,String action){}
 public record PreferenceResponse(String id,String versionId,String topAgent,String fieldKey,String value,long revision,String status,String sourceType,String sourceRef,@com.fasterxml.jackson.annotation.JsonFormat(shape=com.fasterxml.jackson.annotation.JsonFormat.Shape.STRING) Instant expiresAt){static PreferenceResponse of(Preference p){return new PreferenceResponse(p.id(),p.versionId(),p.scope().topLevelAgentId(),p.fieldKey(),p.value(),p.revision(),p.status(),p.sourceType(),p.sourceRef(),p.expiresAt());}}
 public record VersionResponse(String versionId,String value,String status,String sourceType,String sourceRef,@com.fasterxml.jackson.annotation.JsonFormat(shape=com.fasterxml.jackson.annotation.JsonFormat.Shape.STRING) Instant expiresAt){static VersionResponse of(Preference p){return new VersionResponse(p.versionId(),p.value(),p.status(),p.sourceType(),p.sourceRef(),p.expiresAt());}}
 public record PageResponse(List<PreferenceResponse> items,long total,int page,int pageSize){}
 public record DetailResponse(PreferenceResponse preference,List<VersionResponse> history){}
}

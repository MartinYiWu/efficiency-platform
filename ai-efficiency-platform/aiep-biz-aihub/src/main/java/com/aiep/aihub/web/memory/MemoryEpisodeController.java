package com.aiep.aihub.web.memory;

import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.api.memory.MemoryEpisodeContracts.*;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.application.memory.*;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformcore.api.ApiResponse;
import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.*;
import org.springframework.web.bind.annotation.*;

/** 有权人员逐级经验审阅与现有资产候选，HTTP不提供模型自报测量/确认/发布字段。 */
@RestController
@RequestMapping("/api/aihub")
public class MemoryEpisodeController {
    private final MemoryScopePolicy actors;private final MemoryEpisodeService episodes;private final MemoryPromotionService promotions;
    public MemoryEpisodeController(MemoryScopePolicy actors,MemoryEpisodeService episodes,MemoryPromotionService promotions){this.actors=actors;this.episodes=episodes;this.promotions=promotions;}
    @PostMapping("/memory-episodes") public ApiResponse<EpisodeView> create(@RequestBody JsonNode body){fields(body,"topAgent","sessionId","executionId","content","idempotencyKey");var actor=actors.currentActor();return success(episodes.create(actor,new CreateCommand(scope(actor,body),text(body,"executionId"),content(body.path("content")),text(body,"idempotencyKey"))));}
    @GetMapping("/memory-episodes") public ApiResponse<List<EpisodeView>> list(@RequestParam String topAgent,@RequestParam(required=false) String sessionId){var actor=actors.currentActor();return success(episodes.list(actor,scope(actor,topAgent,sessionId)));}
    @GetMapping("/memory-episodes/shared") public ApiResponse<List<EpisodeView>> shared(@RequestParam String shareScopeId){return success(episodes.shared(actors.currentActor(),shareScopeId));}
    @GetMapping("/memory-episodes/{id}") public ApiResponse<EpisodeView> get(@PathVariable String id,@RequestParam String topAgent,@RequestParam(required=false) String sessionId){var actor=actors.currentActor();return success(episodes.get(actor,scope(actor,topAgent,sessionId),id));}
    @PostMapping("/memory-episodes/{id}/decisions") public ApiResponse<EpisodeView> decide(@PathVariable String id,@RequestBody JsonNode body){fields(body,"topAgent","sessionId","expectedRevision","action","idempotencyKey");var actor=actors.currentActor();return success(episodes.decide(actor,scope(actor,body),id,number(body,"expectedRevision"),text(body,"action"),text(body,"idempotencyKey")));}
    @PostMapping("/memory-episodes/{id}/sharing") public ApiResponse<EpisodeView> share(@PathVariable String id,@RequestBody JsonNode body){fields(body,"topAgent","sessionId","expectedRevision","shareScopeId","deidentifiedContent","idempotencyKey");var actor=actors.currentActor();return success(episodes.requestShare(actor,scope(actor,body),id,number(body,"expectedRevision"),text(body,"shareScopeId"),content(body.path("deidentifiedContent")),text(body,"idempotencyKey")));}
    @PostMapping("/memory-episodes/{id}/sharing-approvals") public ApiResponse<EpisodeView> approve(@PathVariable String id,@RequestBody JsonNode body){fields(body,"expectedRevision","idempotencyKey");return success(episodes.approveShare(actors.currentActor(),id,number(body,"expectedRevision"),text(body,"idempotencyKey")));}
    @PostMapping("/memory-episodes/{id}/likes") public ApiResponse<EpisodeView> like(@PathVariable String id,@RequestBody JsonNode body){fields(body,"topAgent","sessionId");var actor=actors.currentActor();return success(episodes.like(actor,scope(actor,body),id));}
    @PostMapping("/memory-episodes/{id}/withdrawals") public ApiResponse<EpisodeView> withdraw(@PathVariable String id,@RequestBody JsonNode body){fields(body,"topAgent","sessionId","expectedRevision","idempotencyKey");var actor=actors.currentActor();return success(episodes.withdraw(actor,scope(actor,body),id,number(body,"expectedRevision"),text(body,"idempotencyKey")));}
    @PostMapping("/memory-promotions") public ApiResponse<PromotionView> promote(@RequestBody JsonNode body){fields(body,"episodeId","topAgent","sessionId","expectedEpisodeRevision","targetType","targetDefinitionId","semanticVersion","changeSummary","graphKey","graphVersion","idempotencyKey");var actor=actors.currentActor();return success(promotions.create(actor,new PromotionCommand(text(body,"episodeId"),scope(actor,body),number(body,"expectedEpisodeRevision"),text(body,"targetType"),text(body,"targetDefinitionId"),text(body,"semanticVersion"),text(body,"changeSummary"),nullable(body,"graphKey"),nullable(body,"graphVersion"),text(body,"idempotencyKey"))));}
    @GetMapping("/memory-promotions") public ApiResponse<List<PromotionView>> promotions(){return success(promotions.list(actors.currentActor()));}
    @GetMapping("/memory-promotions/{id}") public ApiResponse<PromotionView> promotion(@PathVariable String id){return success(promotions.get(actors.currentActor(),id));}
    @PostMapping("/memory-promotions/{id}/regressions") public ApiResponse<PromotionView> regression(@PathVariable String id,@RequestBody JsonNode body){fields(body,"expectedRevision","suiteId","suiteVersion","candidateDigest","reportSha256","totalCases","passedCases","idempotencyKey");long total=number(body,"totalCases"),passed=number(body,"passedCases");if(total>Integer.MAX_VALUE||passed>Integer.MAX_VALUE)invalid();return success(promotions.regression(actors.currentActor(),id,new RegressionCommand(number(body,"expectedRevision"),text(body,"suiteId"),text(body,"suiteVersion"),text(body,"candidateDigest"),text(body,"reportSha256"),(int)total,(int)passed,text(body,"idempotencyKey"))));}
    @PostMapping("/memory-promotions/{id}/publications") public ApiResponse<PromotionView> publish(@PathVariable String id,@RequestBody JsonNode body){fields(body,"expectedRevision","action","idempotencyKey");return success(promotions.publish(actors.currentActor(),id,number(body,"expectedRevision"),text(body,"action"),text(body,"idempotencyKey")));}
    private static Content content(JsonNode body){fields(body,"category","scenario","preconditions","actions","observedResults","denominator","observedFrom","observedUntil","evidenceRefs","applicableVersion","disallowedConditions");return new Content(text(body,"category"),text(body,"scenario"),strings(body,"preconditions"),strings(body,"actions"),text(body,"observedResults"),body.path("denominator").isNull()?null:number(body,"denominator"),instant(body,"observedFrom"),instant(body,"observedUntil"),strings(body,"evidenceRefs"),text(body,"applicableVersion"),strings(body,"disallowedConditions"));}
    private static List<String> strings(JsonNode body,String name){var array=body.path(name);if(!array.isArray())invalid();var result=new ArrayList<String>();for(var value:array){if(!value.isTextual())invalid();result.add(value.textValue());}return result;}
    private static Instant instant(JsonNode body,String name){String value=nullable(body,name);if(value==null)return null;try{return Instant.parse(value);}catch(java.time.DateTimeException invalid){throw new MemoryException("MEMORY_EPISODE_INVALID");}}
    private static MemoryScopeDTO scope(IdentityFacade.Subject actor,JsonNode body){return scope(actor,text(body,"topAgent"),nullable(body,"sessionId"));}
    private static MemoryScopeDTO scope(IdentityFacade.Subject actor,String agent,String session){return new MemoryScopeDTO(actor.tenantId(),actor.userId(),agent,agent,session==null?"TASK_ONLY":"CONVERSATION",session);}
    private static void fields(JsonNode body,String... names){if(body==null||!body.isObject()||body.size()!=names.length)invalid();for(String name:names)if(!body.has(name))invalid();}
    private static String text(JsonNode body,String name){var value=body.path(name);if(!value.isTextual()||value.textValue().isBlank())invalid();return value.textValue();}
    private static String nullable(JsonNode body,String name){return body.path(name).isNull()?null:text(body,name);}
    private static long number(JsonNode body,String name){var value=body.path(name);if(!value.isIntegralNumber()||!value.canConvertToLong()||value.longValue()<0)invalid();return value.longValue();}
    private static void invalid(){throw new MemoryException("MEMORY_EPISODE_INVALID");}
    private static <T>ApiResponse<T> success(T data){return ApiResponse.success(data).withTraceId(MemoryExceptionHandler.trace());}
}

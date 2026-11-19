package com.aiep.aihub.web.memory;

import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.application.memory.*;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformcore.api.ApiResponse;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.*;
import org.springframework.web.bind.annotation.*;

/** 显式索引申请与有限CPU词法召回；业务输入不能提供预算、模型或授权集合。 */
@RestController
@RequestMapping("/api/aihub/memory-semantic")
public class MemorySemanticController {
    private final MemoryScopePolicy scopes;private final MemoryIndexService indexes;private final MemoryRecallService recall;
    public MemorySemanticController(MemoryScopePolicy scopes,MemoryIndexService indexes,MemoryRecallService recall){this.scopes=scopes;this.indexes=indexes;this.recall=recall;}
    @PostMapping("/indexes") public ApiResponse<MemoryIndexService.IndexStatus> index(@RequestBody JsonNode body){
        fields(body,"topAgent","sessionId","itemId","expectedRevision","executionId","idempotencyKey");var actor=scopes.currentActor();
        var expected=body.path("expectedRevision");if(!expected.isIntegralNumber()||!expected.canConvertToLong()||expected.longValue()<1)invalid();
        return success(indexes.request(actor,scope(actor,body),text(body,"itemId"),expected.longValue(),text(body,"executionId"),text(body,"idempotencyKey")));
    }
    @GetMapping("/indexes/{id}") public ApiResponse<MemoryIndexService.IndexStatus> indexStatus(@PathVariable String id,@RequestParam String topAgent,@RequestParam String sessionId){var actor=scopes.currentActor();return success(indexes.get(actor,new MemoryScopeDTO(actor.tenantId(),actor.userId(),topAgent,topAgent,"CONVERSATION",sessionId),id));}
    @PostMapping("/recall") public ApiResponse<MemoryRecallService.Result> recall(@RequestBody JsonNode body){
        if(body.has("query"))fields(body,"topAgent","sessionId","executionId","terms","query");else fields(body,"topAgent","sessionId","executionId","terms");if(!body.path("terms").isArray()||body.path("terms").size()>32)invalid();var terms=new ArrayList<String>();
        for(var term:body.path("terms")){if(!term.isTextual()||term.textValue().isBlank()||term.textValue().codePointCount(0,term.textValue().length())>128)invalid();terms.add(term.textValue());}
        String query=body.has("query")&&!body.path("query").isNull()?text(body,"query"):null;
        if(query!=null&&query.codePointCount(0,query.length())>2048)invalid();
        var actor=scopes.currentActor();return success(recall.recall(actor,scope(actor,body),text(body,"executionId"),terms,query));
    }
    private static MemoryScopeDTO scope(IdentityFacade.Subject actor,JsonNode body){String agent=text(body,"topAgent");return new MemoryScopeDTO(actor.tenantId(),actor.userId(),agent,agent,"CONVERSATION",text(body,"sessionId"));}
    private static void fields(JsonNode body,String... names){if(body==null||!body.isObject()||body.size()!=names.length)invalid();for(var name:names)if(!body.has(name))invalid();}
    private static String text(JsonNode body,String name){var value=body.path(name);if(!value.isTextual()||value.textValue().isBlank())invalid();return value.textValue();}
    private static void invalid(){throw new MemoryException("MEMORY_REQUEST_INVALID");}
    private static <T>ApiResponse<T> success(T value){return ApiResponse.success(value).withTraceId(MemoryExceptionHandler.trace());}
}

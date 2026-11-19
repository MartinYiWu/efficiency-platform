package com.aiep.aihub.web.memory;

import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.api.memory.MemoryProposalContracts.*;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.application.memory.MemoryProposalService;
import com.aiep.aihub.application.memory.MemoryScopePolicy;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformcore.api.ApiResponse;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.*;
import org.springframework.web.bind.annotation.*;

/** 用户候选与CPU决定；HTTP不接tenant/user/来源epoch/用途授权/模型预算。 */
@RestController
@RequestMapping("/api/aihub/memories/proposals")
public class MemoryProposalController {
    private final MemoryScopePolicy scopes;private final MemoryProposalService proposals;
    public MemoryProposalController(MemoryScopePolicy scopes,MemoryProposalService proposals){this.scopes=scopes;this.proposals=proposals;}
    @PostMapping public ApiResponse<BatchView> submit(@RequestBody JsonNode body) {
        fields(body,"topAgent","sessionId","executionId","sourceMessageIds","candidates","idempotencyKey");
        var actor=scopes.currentActor();var sourceIds=new ArrayList<String>();var candidates=new ArrayList<Candidate>();
        if(!body.path("sourceMessageIds").isArray()||!body.path("candidates").isArray())invalid();
        for(var id:body.path("sourceMessageIds")){if(!id.isTextual())invalid();sourceIds.add(id.textValue());}
        for(var candidate:body.path("candidates")) {
            fields(candidate,"kind","fieldKey","value");candidates.add(new Candidate(text(candidate,"kind"),text(candidate,"fieldKey"),text(candidate,"value")));
        }
        var result=proposals.submit(actor,new Submission(scope(actor,text(body,"topAgent"),text(body,"sessionId")),text(body,"executionId"),sourceIds,candidates,text(body,"idempotencyKey")));
        return success(new BatchView(result.taskId(),result.proposals().stream().map(ProposalView::of).toList(),result.actions()));
    }
    @GetMapping public ApiResponse<List<ProposalView>> list(@RequestParam String topAgent,@RequestParam String sessionId,@RequestParam(defaultValue="20") int limit) {
        var actor=scopes.currentActor();return success(proposals.list(actor,scope(actor,topAgent,sessionId),limit).stream().map(ProposalView::of).toList());
    }
    @GetMapping("/{id}") public ApiResponse<ProposalView> get(@PathVariable String id,@RequestParam String topAgent,@RequestParam String sessionId) {
        var actor=scopes.currentActor();return success(ProposalView.of(proposals.get(actor,scope(actor,topAgent,sessionId),id)));
    }
    @PostMapping("/{id}/decisions") public ApiResponse<ProposalView> decide(@PathVariable String id,@RequestBody JsonNode body) {
        fields(body,"topAgent","sessionId","expectedProposalRevision","expectedItemRevision","action","idempotencyKey");
        var actor=scopes.currentActor();Decision decision;
        try{decision=Decision.valueOf(text(body,"action"));}catch(IllegalArgumentException error){throw new MemoryException("MEMORY_PROPOSAL_INVALID");}
        return success(ProposalView.of(proposals.decide(actor,id,new DecisionCommand(scope(actor,text(body,"topAgent"),text(body,"sessionId")),number(body,"expectedProposalRevision"),number(body,"expectedItemRevision"),decision,text(body,"idempotencyKey")))));
    }
    private static MemoryScopeDTO scope(IdentityFacade.Subject actor,String agent,String session){return new MemoryScopeDTO(actor.tenantId(),actor.userId(),agent,agent,"CONVERSATION",session);}
    private static void fields(JsonNode body,String... names){if(body==null||!body.isObject()||body.size()!=names.length)invalid();for(String name:names)if(!body.has(name))invalid();}
    private static String text(JsonNode body,String name){var value=body.path(name);if(!value.isTextual()||value.textValue().isBlank())invalid();return value.textValue();}
    private static long number(JsonNode body,String name){var value=body.path(name);if(!value.isIntegralNumber()||!value.canConvertToLong()||value.longValue()<0)invalid();return value.longValue();}
    private static void invalid(){throw new MemoryException("MEMORY_PROPOSAL_INVALID");}
    private static <T>ApiResponse<T> success(T data){return ApiResponse.success(data).withTraceId(MemoryExceptionHandler.trace());}
    public record ProposalView(String id,String itemId,String topAgent,String sessionId,String fieldKey,String value,
            Action action,Status status,long revision,long expectedItemRevision,
            @com.fasterxml.jackson.annotation.JsonFormat(shape=com.fasterxml.jackson.annotation.JsonFormat.Shape.STRING) java.time.Instant expiresAt,
            String indexStatus,String versionId) {
        static ProposalView of(Proposal proposal){return new ProposalView(proposal.id(),proposal.itemId(),proposal.scope().topLevelAgentId(),proposal.scope().sessionId(),proposal.fieldKey(),proposal.value(),proposal.action(),proposal.status(),proposal.revision(),proposal.expectedItemRevision(),proposal.expiresAt(),proposal.indexStatus(),proposal.versionId());}
        @Override public String toString(){return "MemoryProposalView[redacted]";}
    }
    public record BatchView(String taskId,List<ProposalView> proposals,List<Action> actions) { }
}

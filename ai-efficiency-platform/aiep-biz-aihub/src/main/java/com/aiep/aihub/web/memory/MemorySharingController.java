package com.aiep.aihub.web.memory;

import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.api.memory.MemorySharingContracts.*;
import com.aiep.aihub.application.memory.*;
import com.aiep.platformcore.api.ApiResponse;
import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.*;
import org.springframework.web.bind.annotation.*;

/** 显式记忆授权API；主体由Identity提供，scope不是源业务访问凭据。 */
@RestController
@RequestMapping("/api/aihub/memory-sharing")
public class MemorySharingController {
    private final MemoryScopePolicy actors;private final MemoryAgentGrantService agents;
    private final MemoryScopeMembershipService memberships;private final MemorySharingService sharing;
    public MemorySharingController(MemoryScopePolicy actors,MemoryAgentGrantService agents,MemoryScopeMembershipService memberships,MemorySharingService sharing){this.actors=actors;this.agents=agents;this.memberships=memberships;this.sharing=sharing;}
    @GetMapping("/agent-grants") public ApiResponse<List<GrantView>> grants(@RequestParam String originAgent){return success(agents.list(actors.currentActor(),originAgent));}
    @PostMapping("/agent-grants") public ApiResponse<GrantView> grant(@RequestBody JsonNode body){fields(body,"originAgent","itemId","versionId","targetAgent","expectedItemRevision","expiresAt","idempotencyKey");return success(agents.grant(actors.currentActor(),new GrantCommand(text(body,"originAgent"),text(body,"itemId"),text(body,"versionId"),text(body,"targetAgent"),number(body,"expectedItemRevision"),instant(body,"expiresAt"),text(body,"idempotencyKey"))));}
    @PostMapping("/agent-grants/{id}/withdrawals") public ApiResponse<GrantView> withdrawGrant(@PathVariable String id,@RequestBody JsonNode body){return success(agents.withdraw(actors.currentActor(),id,revision(body)));}
    @GetMapping("/scopes") public ApiResponse<List<ScopeView>> scopes(){return success(memberships.list(actors.currentActor()));}
    @PostMapping("/scopes") public ApiResponse<ScopeView> createScope(@RequestBody JsonNode body){fields(body,"scopeType","departmentId","approverUserId","expiresAt","idempotencyKey");String department=body.path("departmentId").isNull()?null:text(body,"departmentId");return success(memberships.create(actors.currentActor(),new ScopeCommand(text(body,"scopeType"),department,text(body,"approverUserId"),instant(body,"expiresAt"),text(body,"idempotencyKey"))));}
    @PostMapping("/scopes/{id}/approvals") public ApiResponse<ScopeView> approveScope(@PathVariable String id,@RequestBody JsonNode body){return success(memberships.approve(actors.currentActor(),id,revision(body)));}
    @PostMapping("/scopes/{id}/members") public ApiResponse<ScopeView> invite(@PathVariable String id,@RequestBody JsonNode body){fields(body,"userId","expectedRevision","idempotencyKey");return success(memberships.invite(actors.currentActor(),id,new MemberCommand(text(body,"userId"),number(body,"expectedRevision"),text(body,"idempotencyKey"))));}
    @PostMapping("/scopes/{id}/membership") public ApiResponse<ScopeView> membership(@PathVariable String id,@RequestBody JsonNode body){fields(body,"expectedRevision","action","idempotencyKey");return success(sharing.membership(actors.currentActor(),id,new MembershipCommand(number(body,"expectedRevision"),text(body,"action"),text(body,"idempotencyKey"))));}
    @GetMapping("/scopes/{id}/shares") public ApiResponse<List<ShareView>> shares(@PathVariable String id){return success(sharing.listShares(actors.currentActor(),id));}
    @PostMapping("/scopes/{id}/shares") public ApiResponse<ShareView> share(@PathVariable String id,@RequestBody JsonNode body){fields(body,"originAgent","itemId","versionId","expectedItemRevision","allowedAgents","expiresAt","idempotencyKey");if(!body.path("allowedAgents").isArray())invalid();var targets=new ArrayList<String>();for(var target:body.path("allowedAgents")){if(!target.isTextual())invalid();targets.add(target.textValue());}return success(sharing.requestShare(actors.currentActor(),id,new ShareCommand(text(body,"originAgent"),text(body,"itemId"),text(body,"versionId"),number(body,"expectedItemRevision"),targets,instant(body,"expiresAt"),text(body,"idempotencyKey"))));}
    @PostMapping("/shares/{id}/approvals") public ApiResponse<ShareView> approveShare(@PathVariable String id,@RequestBody JsonNode body){return success(sharing.approveShare(actors.currentActor(),id,revision(body)));}
    @PostMapping("/shares/{id}/withdrawals") public ApiResponse<ShareView> withdrawShare(@PathVariable String id,@RequestBody JsonNode body){return success(sharing.withdrawShare(actors.currentActor(),id,revision(body)));}
    private static RevisionCommand revision(JsonNode body){fields(body,"expectedRevision","idempotencyKey");return new RevisionCommand(number(body,"expectedRevision"),text(body,"idempotencyKey"));}
    private static void fields(JsonNode body,String... names){if(body==null||!body.isObject()||body.size()!=names.length)invalid();for(String name:names)if(!body.has(name))invalid();}
    private static String text(JsonNode body,String name){var value=body.path(name);if(!value.isTextual()||value.textValue().isBlank())invalid();return value.textValue();}
    private static long number(JsonNode body,String name){var value=body.path(name);if(!value.isIntegralNumber()||!value.canConvertToLong()||value.longValue()<0)invalid();return value.longValue();}
    private static Instant instant(JsonNode body,String name){try{return Instant.parse(text(body,name));}catch(java.time.DateTimeException error){throw new MemoryException("MEMORY_SHARING_INVALID");}}
    private static void invalid(){throw new MemoryException("MEMORY_SHARING_INVALID");}
    private static <T>ApiResponse<T> success(T result){return ApiResponse.success(result).withTraceId(MemoryExceptionHandler.trace());}
}

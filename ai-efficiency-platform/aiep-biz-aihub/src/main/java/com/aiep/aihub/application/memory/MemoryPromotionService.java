package com.aiep.aihub.application.memory;

import static com.aiep.aihub.application.memory.MemoryScopeMembershipService.*;
import com.aiep.aihub.api.memory.MemoryEpisodeContracts.*;
import com.aiep.aihub.repository.memory.MemoryEpisodeMapper;
import com.aiep.aihub.repository.memory.MemoryEpisodeMapper.PromotionPO;
import com.aiep.aihub.application.management.MemoryPromotionAssetAdapter;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformai.api.dto.MemoryPacketDigest;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.*;
import org.springframework.stereotype.Service;

/** 人工分享→现有DRAFT→独立固定回归证明→人批准发布；任何步骤不授权费用。 */
@Service
public class MemoryPromotionService {
    private final MemoryEpisodeService episodes;private final MemoryEpisodeMapper mapper;private final MemoryPromotionAssetAdapter assets;
    public MemoryPromotionService(MemoryEpisodeService episodes,MemoryEpisodeMapper mapper,MemoryPromotionAssetAdapter assets){this.episodes=episodes;this.mapper=mapper;this.assets=assets;}
    public PromotionView create(IdentityFacade.Subject original,PromotionCommand command) {
        var actor=episodes.current(original,"memory:promotion:create");id(command.idempotencyKey());
        return episodes.transaction.execute(tx->{
            var episode=episodes.refresh(episodes.load(actor.tenantId(),command.episodeId()));episodes.readableShared(actor,episode);
            if(episode.revision()!=command.expectedEpisodeRevision())throw failure("MEMORY_EPISODE_REVISION_CONFLICT");
            var policy=episodes.policy(episode).path("promotion");allowTarget(policy,command);
            String fingerprint=MemoryPacketDigest.canonicalDigest(MemoryEpisodeService.JSON.valueToTree(List.of(actor.userId(),command)));
            var prior=mapper.findPromotionRequest(b(actor.tenantId()),b(command.idempotencyKey()));
            if(prior!=null){if(!fingerprint.equals(prior.fingerprint()))throw failure("MEMORY_IDEMPOTENCY_CONFLICT");return view(prior);}
            var draft=assets.create(actor,command,episodes.content(episode,true));
            var row=new PromotionPO(b(actor.tenantId()),uuid(),episode.id(),b(actor.userId()),command.targetType(),command.targetDefinitionId(),draft.versionId(),draft.digest(),"DRAFT",0,b(command.idempotencyKey()),fingerprint,null,null,null,0,0,null,null);
            one(mapper.insertPromotion(row));return view(row);
        });
    }
    static void allowTarget(JsonNode policy,PromotionCommand command) {
        if(!policy.path("enabled").isBoolean()||!policy.path("enabled").booleanValue())throw failure("FEATURE_DISABLED");
        if(command.targetType()==null||!Set.of("PROMPT","WORKFLOW","SKILL").contains(command.targetType()))throw failure("MEMORY_PROMOTION_TARGET_INVALID");
        var allowed=policy.path("PROMPT".equals(command.targetType())?"allowedPromptIds":"allowedAgentIds");
        if(!allowed.isArray()||!contains(allowed,command.targetDefinitionId()))throw failure("MEMORY_SCOPE_DENIED");
        if(!"PROMPT".equals(command.targetType())&&!contains(policy.path("allowedGraphRefs"),command.graphKey()+"@"+command.graphVersion()))throw failure("MEMORY_PROMOTION_TARGET_INVALID");
    }
    public List<PromotionView> list(IdentityFacade.Subject original) {
        var actor=episodes.current(original,null);return episodes.transaction.execute(tx->{
            boolean review=actor.permissions().contains("memory:promotion:regression"),publish=actor.permissions().contains("memory:promotion:publish");
            var result=new ArrayList<PromotionView>();
            for(var row:mapper.listPromotions(b(actor.tenantId()),b(actor.userId()),review,publish)) {
                if(!Arrays.equals(row.ownerId(),b(actor.userId()))
                        &&!(review&&"DRAFT".equals(row.status()))
                        &&!(publish&&"REGRESSION_PASSED".equals(row.status())&&!Arrays.equals(row.regressionReviewerId(),b(actor.userId()))))continue;
                try {var current=refresh(actor,row);if(!"REVOKED".equals(current.status()))result.add(view(current));}
                catch(com.aiep.aihub.api.memory.MemoryContracts.MemoryException denied) {
                    if(!Set.of("MEMORY_SCOPE_DENIED","MEMORY_NOT_FOUND","MEMORY_SOURCE_CHANGED","MEMORY_PROMOTION_SOURCE_REVOKED").contains(denied.code()))throw denied;
                }
            }
            return List.copyOf(result);
        });
    }
    public PromotionView get(IdentityFacade.Subject original,String id) {
        var actor=episodes.current(original,null);return episodes.transaction.execute(tx->view(refresh(actor,load(actor.tenantId(),id))));
    }
    /** 仅独立授权回归审核员可提交人工签认；不把模型passed或旧RAG run视作候选测试。 */
    public PromotionView regression(IdentityFacade.Subject original,String id,RegressionCommand command) {
        var actor=episodes.current(original,"memory:promotion:regression");id(command.idempotencyKey());
        return episodes.transaction.execute(tx->{var row=refresh(actor,load(actor.tenantId(),id));
            if(Arrays.equals(row.ownerId(),b(actor.userId()))||!"DRAFT".equals(row.status())||row.revision()!=command.expectedRevision())throw failure("MEMORY_PROMOTION_REVISION_CONFLICT");
            var episode=episodes.load(actor.tenantId(),text(row.episodeId()));var policy=episodes.policy(episode).path("promotion").path("regression");
            validateRegression(policy,row.candidateDigest(),command);
            if(!assets.digest(row.targetType(),row.targetVersionId()).equals(row.candidateDigest()))throw failure("MEMORY_PROMOTION_ASSET_CHANGED");
            one(mapper.regression(row,command,b(actor.userId())));return view(load(actor.tenantId(),id));});
    }
    static void validateRegression(JsonNode policy,String digest,RegressionCommand command) {
        if(!policy.path("suiteId").isTextual()||!policy.path("suiteVersion").isTextual()||!policy.path("minCases").isIntegralNumber()
                ||!policy.path("minCases").canConvertToInt()
                ||!policy.path("suiteId").textValue().equals(command.suiteId())||!policy.path("suiteVersion").textValue().equals(command.suiteVersion())
                ||policy.path("minCases").intValue()<1||command.totalCases()>1000000||command.totalCases()<policy.path("minCases").intValue()||command.passedCases()!=command.totalCases()
                ||!digest.equals(command.candidateDigest())||command.reportSha256()==null||!command.reportSha256().matches("[0-9a-f]{64}"))throw failure("MEMORY_PROMOTION_REGRESSION_REQUIRED");
    }
    public PromotionView publish(IdentityFacade.Subject original,String id,long expected,String action,String request) {
        var actor=episodes.current(original,"memory:promotion:publish");id(request);
        if(!"APPROVE_PUBLISH".equals(action))throw failure("MEMORY_PROMOTION_INVALID");
        return episodes.transaction.execute(tx->{var row=refresh(actor,load(actor.tenantId(),id));
            if(!"REGRESSION_PASSED".equals(row.status())||row.revision()!=expected||row.regressionReviewerId()==null
                    ||Arrays.equals(row.ownerId(),b(actor.userId()))||Arrays.equals(row.regressionReviewerId(),b(actor.userId())))throw failure("MEMORY_PROMOTION_REVISION_CONFLICT");
            assets.publish(actor,row.targetType(),row.targetVersionId(),row.candidateDigest());
            one(mapper.finishPromotion(row,"PUBLISHED",b(actor.userId())));return view(load(actor.tenantId(),id));});
    }
    private PromotionPO refresh(IdentityFacade.Subject actor,PromotionPO row) {
        var episode=episodes.refresh(episodes.load(actor.tenantId(),text(row.episodeId())));
        if("REVOKED".equals(episode.status())) {
            var current=load(actor.tenantId(),text(row.id()));
            if(!"REVOKED".equals(current.status())){one(mapper.finishPromotion(current,"REVOKED",b(actor.userId())));current=load(actor.tenantId(),text(row.id()));}
            if(!Arrays.equals(current.ownerId(),b(actor.userId())))throw failure("MEMORY_SCOPE_DENIED");
            return current;
        }
        episodes.readableShared(actor,episode);return row;
    }
    private PromotionPO load(String tenant,String id){var row=mapper.lockPromotion(b(tenant),b(id));if(row==null)throw failure("MEMORY_NOT_FOUND");return row;}
    private static PromotionView view(PromotionPO row){return new PromotionView(text(row.id()),text(row.episodeId()),row.targetType(),row.targetDefinitionId(),row.targetVersionId(),row.candidateDigest(),row.status(),row.revision(),row.regressionReportSha256());}
    private static boolean contains(JsonNode array,String value){if(!array.isArray())return false;for(var child:array)if(child.isTextual()&&child.textValue().equals(value))return true;return false;}
}

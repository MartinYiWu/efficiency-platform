package com.aiep.aihub.repository.memory;

import java.time.Instant;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface MemoryEpisodeMapper {
    record EpisodePO(byte[] tenantId,byte[] id,byte[] ownerId,String domain,byte[] sessionId,byte[] executionId,
            String scopeJson,String dependenciesJson,byte[] policyId,byte[] policyVersionId,String status,long revision,
            Instant expiresAt,String keyVersion,byte[] encryptedPayload,byte[] nonce,byte[] authTag,byte[] contentHmac,
            byte[] shareScopeId,byte[] shareOwnerSessionRef,String sharedKeyVersion,byte[] sharedPayload,byte[] sharedNonce,byte[] sharedTag,byte[] sharedHmac,
            byte[] shareApproverId,byte[] requestId,String fingerprint) {
        @Override public String toString(){return "MemoryEpisodeRow[redacted]";}
    }
    record PromotionPO(byte[] tenantId,byte[] id,byte[] episodeId,byte[] ownerId,String targetType,String targetDefinitionId,
            String targetVersionId,String candidateDigest,String status,long revision,byte[] requestId,String fingerprint,
            String regressionSuiteId,String regressionSuiteVersion,String regressionReportSha256,int totalCases,int passedCases,byte[] regressionReviewerId,byte[] publisherId) { }
    record SharedPO(String keyVersion,byte[] payload,byte[] nonce,byte[] tag,byte[] hmac) { }
    EpisodePO lockEpisode(@Param("tenant") byte[] tenant,@Param("id") byte[] id);
    EpisodePO findEpisodeRequest(@Param("tenant") byte[] tenant,@Param("request") byte[] request);
    List<EpisodePO> listEpisodes(@Param("tenant") byte[] tenant,@Param("user") byte[] user,@Param("domain") String domain,@Param("session") byte[] session);
    List<EpisodePO> listShared(@Param("tenant") byte[] tenant,@Param("scope") byte[] scope);
    int insertEpisode(@Param("row") EpisodePO row);
    int transition(@Param("row") EpisodePO row,@Param("status") String status);
    int requestShare(@Param("row") EpisodePO row,@Param("scope") byte[] scope,@Param("ownerSession") byte[] ownerSession,@Param("sealed") SharedPO sealed);
    int approveShare(@Param("row") EpisodePO row,@Param("actor") byte[] actor);
    int scrub(@Param("row") EpisodePO row);
    int insertLike(@Param("tenant") byte[] tenant,@Param("episode") byte[] episode,@Param("user") byte[] user);
    long countLikes(@Param("tenant") byte[] tenant,@Param("episode") byte[] episode);
    PromotionPO lockPromotion(@Param("tenant") byte[] tenant,@Param("id") byte[] id);
    PromotionPO findPromotionRequest(@Param("tenant") byte[] tenant,@Param("request") byte[] request);
    List<PromotionPO> listPromotions(@Param("tenant") byte[] tenant,@Param("user") byte[] user,
            @Param("canReview") boolean canReview,@Param("canPublish") boolean canPublish);
    int insertPromotion(@Param("row") PromotionPO row);
    int regression(@Param("row") PromotionPO row,@Param("command") com.aiep.aihub.api.memory.MemoryEpisodeContracts.RegressionCommand command,@Param("actor") byte[] actor);
    int finishPromotion(@Param("row") PromotionPO row,@Param("status") String status,@Param("actor") byte[] actor);
    PromotionPO findAssetPromotion(@Param("type") String type,@Param("version") String version);
    int assetSourcesCurrent(@Param("tenant") byte[] tenant,@Param("episode") byte[] episode);
}

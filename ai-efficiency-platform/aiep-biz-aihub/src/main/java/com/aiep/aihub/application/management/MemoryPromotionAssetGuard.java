package com.aiep.aihub.application.management;

import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.repository.memory.MemoryEpisodeMapper;
import com.aiep.identity.api.IdentityFacade;
import java.util.Arrays;
import org.springframework.stereotype.Service;

/** 仅标记为memory-episode的现有资产调用本保护；旧普通资产不查询新表。 */
@Service
public class MemoryPromotionAssetGuard {
    public static final String MARKER="memory-episode:";
    private final MemoryEpisodeMapper mapper;private final IdentityFacade identity;
    public MemoryPromotionAssetGuard(MemoryEpisodeMapper mapper,IdentityFacade identity){this.mapper=mapper;this.identity=identity;}
    public void transition(String type,String version,String target,IdentityFacade.Subject actor) {
        if("RETIRED".equals(target))return;
        if(actor==null||actor.sessionRef()==null)throw new MemoryException("MEMORY_PROMOTION_APPROVAL_ROUTE_REQUIRED");
        var live=identity.refresh(actor.tenantId(),actor.userId(),actor.sessionRef()).orElseThrow(()->new MemoryException("MEMORY_IDENTITY_REQUIRED"));
        if(!actor.tenantId().equals(live.tenantId())||!actor.userId().equals(live.userId())||!actor.sessionRef().equals(live.sessionRef())||!live.permissions().contains("memory:promotion:publish"))throw new MemoryException("MEMORY_SCOPE_DENIED");
        var row=mapper.findAssetPromotion(type,version);
        if(row==null||!Arrays.equals(row.tenantId(),com.aiep.aihub.repository.memory.MemoryMapper.identity(live.tenantId()))
                ||!"REGRESSION_PASSED".equals(row.status())||mapper.assetSourcesCurrent(row.tenantId(),row.episodeId())!=1)throw new MemoryException("MEMORY_PROMOTION_SOURCE_REVOKED");
    }
    public void deploy(String type,String version) {
        var row=mapper.findAssetPromotion(type,version);
        if(row==null||!"PUBLISHED".equals(row.status())||mapper.assetSourcesCurrent(row.tenantId(),row.episodeId())!=1)throw new MemoryException("MEMORY_PROMOTION_SOURCE_REVOKED");
    }
}

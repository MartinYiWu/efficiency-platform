package com.aiep.aihub.repository.memory;

import java.time.Instant;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface MemoryKnowledgeMapper {
    int claimEvent(@Param("tenant") byte[] tenant,@Param("event") byte[] event);
    int insertSource(@Param("tenant") byte[] tenant,@Param("id") byte[] id,@Param("base") byte[] base,@Param("version") byte[] version,@Param("expires") Instant expires);
    List<SourcePO> listSources(@Param("tenant") byte[] tenant,@Param("base") byte[] base);
    int revoke(@Param("tenant") byte[] tenant,@Param("id") byte[] id);
    List<DeliveryPO> due();
    int claim(@Param("row") DeliveryPO row,@Param("token") byte[] token);
    int finish(@Param("row") DeliveryPO row,@Param("token") byte[] token,@Param("success") boolean success);
    record SourcePO(byte[] id,long grantEpoch,long sourceEpoch,long deletionEpoch) { }
    record DeliveryPO(byte[] tenantId,byte[] eventId,byte[] sourceId,long epoch,int attempts) { }
}

package com.aiep.aihub.repository.memory;

import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface MemoryLifecycleMapper {
 List<Delivery> due(@Param("limit") int limit);
 int claim(@Param("delivery") Delivery delivery,@Param("token") byte[] token);
 int release(@Param("delivery") Delivery delivery,@Param("token") byte[] token);
 int sourceTombstone(@Param("tenant") byte[] tenant,@Param("source") byte[] source,@Param("epoch") long epoch);
 List<VersionProof> versionProofs(@Param("tenant") byte[] tenant,@Param("item") byte[] item,@Param("version") byte[] version);
 record VersionProof(String status,String policyJson) {}
 record Delivery(byte[] tenantId,byte[] eventId,byte[] jobId,long deletionEpoch,long revision) {}
}

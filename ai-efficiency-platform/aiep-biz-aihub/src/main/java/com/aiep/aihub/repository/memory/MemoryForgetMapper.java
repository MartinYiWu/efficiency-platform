package com.aiep.aihub.repository.memory;

import com.aiep.aihub.repository.memory.MemoryMapper.*;
import java.time.Instant;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 忘记流程的本地持久端口；所有写入由应用层按source→item→version锁顺序执行。 */
@Mapper
public interface MemoryForgetMapper {
 List<SourcePO> listItemSources(@Param("tenant") byte[] tenant,@Param("item") byte[] item);
 List<SourceIdPO> listItemSourceIdsCurrent(@Param("tenant") byte[] tenant,@Param("item") byte[] item);
 SourcePO lockSource(@Param("tenant") byte[] tenant,@Param("id") byte[] id);
 SourceOwnerPO sourceOwner(@Param("tenant") byte[] tenant,@Param("id") byte[] id);
 List<DependencyPO> listSourcesDependenciesCurrent(@Param("tenant") byte[] tenant,@Param("sources") List<byte[]> sources);
 List<DependencyPO> listSourceDependencies(@Param("tenant") byte[] tenant,@Param("source") byte[] source);
 int revokeSource(@Param("source") SourcePO source);
 int insertSourceSuppression(@Param("item") MemoryItemPO item,@Param("source") SourcePO source,@Param("id") byte[] id);
 SuppressionPO findFieldSuppression(@Param("item") MemoryItemPO item);
 SuppressionPO findSuppression(@Param("tenant") byte[] tenant,@Param("id") byte[] id);
 int insertFieldSuppression(@Param("item") MemoryItemPO item,@Param("id") byte[] id);
 int deactivateSuppression(@Param("tenant") byte[] tenant,@Param("id") byte[] id,@Param("epoch") long epoch);
 int revokeItem(@Param("item") MemoryItemPO item);
 int revokeVersions(@Param("tenant") byte[] tenant,@Param("item") byte[] item,@Param("grant") long grant,@Param("source") long source,@Param("deletion") long deletion);
 JobPO findJob(@Param("tenant") byte[] tenant,@Param("id") byte[] id);
 JobPO readJob(@Param("tenant") byte[] tenant,@Param("id") byte[] id);
 JobPO findItemJob(@Param("tenant") byte[] tenant,@Param("item") byte[] item,@Param("epoch") long epoch);
 JobPO findRequestedJob(@Param("tenant") byte[] tenant,@Param("item") byte[] item,@Param("request") byte[] request);
 int countSourceSuppression(@Param("tenant") byte[] tenant,@Param("source") byte[] source,@Param("version") byte[] version);
 int insertJob(@Param("job") JobPO job);
 int updateJob(@Param("job") JobPO job,@Param("expected") long expected);
 int scrubVersions(@Param("tenant") byte[] tenant,@Param("item") byte[] item,@Param("epoch") long epoch);
 int countPendingVersions(@Param("tenant") byte[] tenant,@Param("item") byte[] item);
 int completeItem(@Param("tenant") byte[] tenant,@Param("item") byte[] item,@Param("epoch") long epoch,@Param("revision") long revision);
 int completeOutbox(@Param("tenant") byte[] tenant,@Param("event") byte[] event);
 int insertReauthorizationDecision(@Param("decision") DecisionPO decision,@Param("suppression") long suppression);
 int insertReauthorizedVersion(@Param("version") VersionRow version,@Param("grant") long grant,@Param("source") long source,@Param("deletion") long deletion);
 int insertReauthorizedSource(@Param("tenant") byte[] tenant,@Param("id") byte[] id,@Param("decision") byte[] decision,@Param("version") byte[] version,@Param("expires") Instant expires,@Param("grant") long grant,@Param("source") long source,@Param("deletion") long deletion);
 int insertReauthorizedDependency(@Param("tenant") byte[] tenant,@Param("sourceId") byte[] sourceId,@Param("item") byte[] item,@Param("version") byte[] version,@Param("grant") long grant,@Param("source") long source,@Param("deletion") long deletion);
 int reauthorizeItem(@Param("item") MemoryItemPO item,@Param("version") byte[] version);
 record SourcePO(byte[] tenantId,byte[] id,String sourceType,byte[] sourceObjectRef,byte[] sourceVersion,long grantEpoch,long sourceEpoch,long deletionEpoch,Instant retentionDeadline){}
 record SourceIdPO(byte[] sourceId){}
 record SourceOwnerPO(byte[] ownerId,String domain,String originTopAgentId,byte[] itemId){}
 record SuppressionPO(byte[] tenantId,byte[] id,String suppressionKind,byte[] sourceId,byte[] sourceVersion,long epoch,boolean active){}
 record DependencyPO(byte[] sourceId,String sourceType,byte[] sourceVersion,long grantEpoch,long sourceEpoch,long deletionEpoch,String targetType,byte[] targetId,byte[] targetVersion,byte[] executionId,byte[] rootThreadRef,byte[] childThreadRef,byte[] checkpointNamespace){}
 record JobPO(byte[] tenantId,byte[] id,byte[] itemId,long deletionEpoch,byte[] requestId,byte[] requestedBy,String status,int requiredTargets,int completedTargets,long revision,int attempts,Instant deadline,String receipts){}
}

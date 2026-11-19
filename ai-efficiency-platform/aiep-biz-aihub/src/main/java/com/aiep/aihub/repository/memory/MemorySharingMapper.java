package com.aiep.aihub.repository.memory;

import java.time.Instant;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface MemorySharingMapper {
    record ScopePO(byte[] tenantId,byte[] id,String scopeType,byte[] departmentId,byte[] ownerId,byte[] approverId,
            String status,long revision,Instant expiresAt,byte[] requestId,String fingerprint) { }
    record MemberPO(byte[] tenantId,byte[] scopeId,byte[] userId,String status,long revision,byte[] requestId) { }
    record GrantPO(byte[] tenantId,byte[] id,byte[] scopeId,byte[] ownerId,byte[] itemId,byte[] versionId,
            String fieldKey,String originAgent,String allowedAgentsJson,String status,long revision,long itemRevision,
            Instant expiresAt,byte[] requestId,String fingerprint) { }
    record ProjectionPO(byte[] tenantId,byte[] id,byte[] grantId,byte[] userId,String targetAgent,long grantRevision,
            long memberRevision,String state,Instant expiresAt,Instant cleanupDeadline) { }
    record DeliveryPO(byte[] tenantId,byte[] eventId,byte[] projectionId,long epoch,int attempts,Instant cleanupDeadline) { }
    ScopePO lockScope(@Param("tenant") byte[] tenant,@Param("id") byte[] id);
    List<ScopePO> listScopes(@Param("tenant") byte[] tenant,@Param("user") byte[] user);
    ScopePO findScopeRequest(@Param("tenant") byte[] tenant,@Param("request") byte[] request);
    int insertScope(@Param("row") ScopePO row);
    int approveScope(@Param("row") ScopePO row);
    MemberPO lockMember(@Param("tenant") byte[] tenant,@Param("scope") byte[] scope,@Param("user") byte[] user);
    List<MemberPO> listMembers(@Param("tenant") byte[] tenant,@Param("scope") byte[] scope);
    int insertMember(@Param("row") MemberPO row);
    int updateMember(@Param("row") MemberPO row,@Param("status") String status,@Param("request") byte[] request);
    int advanceScope(@Param("row") ScopePO row);
    GrantPO lockGrant(@Param("tenant") byte[] tenant,@Param("id") byte[] id);
    GrantPO findGrantRequest(@Param("tenant") byte[] tenant,@Param("request") byte[] request);
    List<GrantPO> listGrants(@Param("tenant") byte[] tenant,@Param("owner") byte[] owner,@Param("origin") String origin);
    List<GrantPO> listScopeGrants(@Param("tenant") byte[] tenant,@Param("scope") byte[] scope);
    int insertGrant(@Param("row") GrantPO row);
    int updateGrant(@Param("row") GrantPO row,@Param("status") String status);
    int insertProjection(@Param("row") ProjectionPO row);
    ProjectionPO lockProjection(@Param("tenant") byte[] tenant,@Param("id") byte[] id);
    List<ProjectionPO> listGrantProjections(@Param("tenant") byte[] tenant,@Param("grant") byte[] grant);
    List<ProjectionPO> listMemberProjections(@Param("tenant") byte[] tenant,@Param("scope") byte[] scope,@Param("user") byte[] user);
    List<ProjectionPO> listReadable(@Param("tenant") byte[] tenant,@Param("user") byte[] user,@Param("agent") String agent);
    int projectionCurrent(@Param("tenant") byte[] tenant,@Param("id") byte[] id,@Param("user") byte[] user,@Param("agent") String agent);
    int revokeProjection(@Param("row") ProjectionPO row);
    int insertProjectionSource(@Param("row") ProjectionPO row);
    int revokeProjectionSource(@Param("row") ProjectionPO row);
    List<DeliveryPO> due(@Param("limit") int limit);
    int claim(@Param("row") DeliveryPO row,@Param("token") byte[] token);
    int finishDelivery(@Param("row") DeliveryPO row,@Param("token") byte[] token,@Param("complete") boolean complete);
}

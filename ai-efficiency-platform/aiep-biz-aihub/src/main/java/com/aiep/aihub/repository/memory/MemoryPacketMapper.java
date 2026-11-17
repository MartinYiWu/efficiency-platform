package com.aiep.aihub.repository.memory;

import com.aiep.platformai.api.dto.MemoryContextPacket.Dependency;
import java.time.Instant;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 真实来源状态和完整反向血缘；不按展示引用裁剪。 */
@Mapper
public interface MemoryPacketMapper {
    SourceState findSource(@Param("tenant") byte[] tenant, @Param("id") byte[] id);
    List<Dependency> findDependencies(@Param("tenant") byte[] tenant, @Param("type") String type,
            @Param("target") byte[] target, @Param("version") byte[] version);
    int insertDependency(@Param("tenant") byte[] tenant, @Param("source") byte[] source,
            @Param("type") String type, @Param("target") byte[] target, @Param("version") byte[] version,
            @Param("execution") byte[] execution, @Param("grantEpoch") long grantEpoch,
            @Param("sourceEpoch") long sourceEpoch, @Param("deletionEpoch") long deletionEpoch);
    record SourceState(String sourceType, byte[] id, byte[] sourceVersion, long grantEpoch,
            long sourceEpoch, long deletionEpoch, Instant retentionDeadline, boolean blocked) { }
    PacketRow findPacket(@Param("tenant") byte[] tenant, @Param("execution") byte[] execution);
    int insertPacket(@Param("row") PacketRow row);
    String findUserMessageHash(@Param("tenant") byte[] tenant, @Param("user") byte[] user,
            @Param("domain") String domain, @Param("session") byte[] session, @Param("message") byte[] message);
    int insertInputSource(@Param("tenant") byte[] tenant, @Param("source") byte[] source,
            @Param("message") byte[] message, @Param("version") byte[] version, @Param("expires") Instant expires);
    record PacketRow(byte[] tenantId, byte[] executionId, byte[] packetId, long packetRevision,
            byte[] userId, byte[] taskId, String scopeJson, String policyJson, String grantsJson,
            String referencesJson, String dependenciesJson, String requestDigest, String packetDigest,
            String semanticDigest, String semanticInputHash, byte[] parentAuthorizationRef,
            long executionRevision, long grantEpoch, long sourceEpoch, long deletionEpoch,
            long originalDeadline, long issuedAt, long expiresAt) { }
}

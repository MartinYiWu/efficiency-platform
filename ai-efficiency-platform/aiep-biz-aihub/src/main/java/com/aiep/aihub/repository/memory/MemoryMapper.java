package com.aiep.aihub.repository.memory;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Set;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 记忆本地事务的持久端口；身份/原授权由应用层给定，不包含模型或网络调用。 */
@Mapper
public interface MemoryMapper {
    SourceOwnerPO findOperationOwner(@Param("tenant") byte[] tenant, @Param("user") byte[] user, @Param("session") byte[] session);
    SourceOwnerPO findCustomerServiceOwner(@Param("tenant") byte[] tenant, @Param("user") byte[] user, @Param("session") byte[] session);
    SessionBindingPO findSessionBinding(@Param("tenant") byte[] tenant, @Param("user") byte[] user, @Param("session") byte[] session);
    int insertSessionBinding(@Param("binding") SessionBindingPO binding);
    int insertItem(@Param("item") MemoryItemPO item);
    MemoryItemPO findItemForUpdate(@Param("tenant") byte[] tenant, @Param("id") byte[] id);
    int compareAndSetCurrent(@Param("tenant") byte[] tenant, @Param("id") byte[] id,
            @Param("expectedRevision") long expectedRevision, @Param("currentVersion") byte[] currentVersion,
            @Param("lifecycle") String lifecycle);
    int insertVersion(@Param("version") MemoryVersionPO version);
    List<DependencyTargetPO> findDependents(@Param("tenant") byte[] tenant, @Param("source") byte[] source);
    int insertOutbox(@Param("tenant") byte[] tenant, @Param("event") byte[] event, @Param("item") byte[] item,
            @Param("version") byte[] version, @Param("type") String type, @Param("epoch") long epoch);
    int advanceTombstone(@Param("tenant") byte[] tenant, @Param("type") String type, @Param("target") byte[] target,
            @Param("deletionEpoch") long deletionEpoch, @Param("grantEpoch") long grantEpoch, @Param("sourceEpoch") long sourceEpoch);

    PolicyPO findPublishedPolicy(@Param("tenant") byte[] tenant, @Param("domain") String domain);
    PolicyPO findPolicyVersion(@Param("tenant") byte[] tenant,@Param("policy") byte[] policy,@Param("version") byte[] version);
    List<VersionPolicyPO> listVersionPolicies(@Param("tenant") byte[] tenant,@Param("versions") List<VersionIdentityPO> versions);
    MemoryItemPO findPreferenceItem(@Param("tenant") byte[] tenant, @Param("user") byte[] user, @Param("domain") String domain, @Param("field") String field);
    List<MemoryItemPO> listPreferenceItems(@Param("tenant") byte[] tenant, @Param("user") byte[] user, @Param("domain") String domain);
    VersionRow findPreferenceVersion(@Param("tenant") byte[] tenant, @Param("item") byte[] item, @Param("version") byte[] version);
    List<VersionRow> listPreferenceVersions(@Param("tenant") byte[] tenant, @Param("item") byte[] item);
    DecisionPO findPreferenceDecision(@Param("tenant") byte[] tenant, @Param("request") byte[] request);
    int insertPreferenceDecision(@Param("decision") DecisionPO decision);
    int insertPreferenceVersion(@Param("version") VersionRow version);
    int clearPreferenceCurrent(@Param("tenant") byte[] tenant,@Param("item") byte[] item,@Param("revision") long revision,@Param("version") byte[] version);
    int retirePreferenceVersion(@Param("tenant") byte[] tenant,@Param("item") byte[] item,@Param("version") byte[] version);
    int insertPreferenceSource(@Param("tenant") byte[] tenant,@Param("source") byte[] source,@Param("decision") byte[] decision,@Param("version") byte[] version,@Param("expires") java.time.Instant expires);
    int insertPreferenceDependency(@Param("tenant") byte[] tenant,@Param("source") byte[] source,@Param("item") byte[] item,@Param("version") byte[] version);
    int countPreferenceSuppression(@Param("tenant") byte[] tenant,@Param("user") byte[] user,@Param("domain") String domain,@Param("scope") byte[] scope,@Param("field") String field);
    record PolicyPO(byte[] id,byte[] versionId,String policyJson,byte[] contentHmac,String schemaVersion) { }
    record VersionIdentityPO(byte[] itemId,byte[] versionId) { }
    record VersionPolicyPO(byte[] itemId,byte[] versionId,byte[] policyId,byte[] policyVersionId,String policyJson,String schemaVersion) { }
    record DecisionPO(byte[] tenantId,byte[] id,byte[] itemId,byte[] targetVersionId,byte[] actorId,String decisionType,byte[] requestId,long expectedRevision,long resultingRevision) { }
    record VersionRow(byte[] tenantId,byte[] itemId,byte[] id,String status,byte[] encryptedPayload,String keyVersion,byte[] nonce,byte[] authTag,byte[] contentHmac,byte[] policyId,byte[] policyVersionId,byte[] decisionId,byte[] supersedesVersionId,java.time.Instant expiresAt,long revision,long grantEpoch,long sourceEpoch,long deletionEpoch) {
        public VersionRow(byte[] tenantId,byte[] itemId,byte[] id,String status,byte[] encryptedPayload,String keyVersion,byte[] nonce,byte[] authTag,byte[] contentHmac,byte[] policyId,byte[] policyVersionId,byte[] decisionId,byte[] supersedesVersionId,java.time.Instant expiresAt,long revision) {
            this(tenantId,itemId,id,status,encryptedPayload,keyVersion,nonce,authTag,contentHmac,policyId,policyVersionId,decisionId,supersedesVersionId,expiresAt,revision,0,0,0);
        }
    }

    /** 128个Unicode字符/512字节；保留大小写及尾空格，拒绝非法代理字符。 */
    static byte[] identity(String value) {
        if (value == null || value.isBlank() || value.codePointCount(0,value.length()) > 128
                || value.codePoints().anyMatch(cp -> cp >= 0xd800 && cp <= 0xdfff))
            throw new IllegalArgumentException("MEMORY_IDENTITY_INVALID");
        byte[] bytes=value.getBytes(StandardCharsets.UTF_8);
        if(bytes.length>512) throw new IllegalArgumentException("MEMORY_IDENTITY_INVALID");
        return bytes;
    }

    /** 无损规范USER_PRIVATE作用域；长度前缀避免分隔符歧义，128emoji仍不截断。 */
    static byte[] privateScope(String user, String originTopAgent) {
        if(originTopAgent == null || !Set.of("operations","customer-service","hr").contains(originTopAgent))
            throw new IllegalArgumentException("MEMORY_ORIGIN_AGENT_INVALID");
        byte[] subject=identity(user), agent=originTopAgent.getBytes(StandardCharsets.US_ASCII);
        return ByteBuffer.allocate(8+subject.length+agent.length).put("up1:".getBytes(StandardCharsets.US_ASCII))
                .putInt(subject.length).put(subject).put(agent).array();
    }

    /** AAD使用独立版本前缀及四个长度前缀字段；不含密钥或正文。 */
    static byte[] aad(byte[] tenant, byte[] item, byte[] version, String keyVersion) {
        if(keyVersion==null || keyVersion.isBlank() || keyVersion.length()>128 || keyVersion.chars().anyMatch(cp->cp>127))
            throw new IllegalArgumentException("MEMORY_KEY_VERSION_INVALID");
        byte[] key=keyVersion.getBytes(StandardCharsets.US_ASCII);
        int size=4+16+tenant.length+item.length+version.length+key.length;
        ByteBuffer result=ByteBuffer.allocate(size).putInt(1);
        for(byte[] part:new byte[][] {tenant,item,version,key}) result.putInt(part.length).put(part);
        return result.array();
    }

    record SourceOwnerPO(byte[] tenantId, byte[] userId, byte[] sessionId) { }
    record SessionBindingPO(byte[] tenantId, byte[] id, byte[] userId, String domain, String topLevelAgentId,
            byte[] sessionId, String sessionKind, String originalObjectType, byte[] originalObjectId) { }
    record MemoryItemPO(byte[] tenantId, byte[] id, String subjectType, byte[] subjectId, byte[] ownerId, String domain,
            String originTopAgentId, String scopeType, byte[] scopeId, String purpose, String fieldKey,
            String lifecycle, long revision, byte[] currentVersionId, long grantEpoch, long sourceEpoch, long deletionEpoch) { }
    record MemoryVersionPO(byte[] tenantId, byte[] itemId, byte[] id, String status, byte[] encryptedPayload,
            String keyVersion, byte[] nonce, byte[] authTag, byte[] contentHmac, String payloadSchema,
            byte[] policyId, byte[] policyVersionId, byte[] decisionId) { }
    record DependencyTargetPO(String targetType, byte[] targetId, byte[] targetVersion,
            byte[] executionId, byte[] rootThreadRef, byte[] childThreadRef, byte[] checkpointNamespace) { }
}

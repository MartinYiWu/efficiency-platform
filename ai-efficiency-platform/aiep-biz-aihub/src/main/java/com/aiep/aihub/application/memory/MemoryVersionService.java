package com.aiep.aihub.application.memory;
import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.repository.memory.MemoryMapper;
import com.aiep.aihub.repository.memory.MemoryMapper.*;
import java.time.Instant;
import org.springframework.stereotype.Service;

/** 更正顺序受D10触发器保护：先清指针，再退役，再新增不可变版本，最后CAS。 */
@Service
public class MemoryVersionService {
 private final MemoryMapper mapper;private final MemoryValueCodec codec;
 public MemoryVersionService(MemoryMapper mapper,MemoryValueCodec codec){this.mapper=mapper;this.codec=codec;}
 public VersionRow replace(MemoryItemPO item,byte[] version,byte[] decision,String value,MemoryPolicyService.Published policy){
  MemoryPolicyService.requireArtifactPolicy(mapper.findPolicyVersion(item.tenantId(),policy.id(),policy.versionId()));
  if(item.currentVersionId()!=null){
   requireOne(mapper.clearPreferenceCurrent(item.tenantId(),item.id(),item.revision(),item.currentVersionId()));
   requireOne(mapper.retirePreferenceVersion(item.tenantId(),item.id(),item.currentVersionId()));
  }
  var sealed=codec.seal(item.tenantId(),item.id(),version,value);var expires=Instant.now().plusSeconds(policy.retentionSeconds());
  var row=new VersionRow(item.tenantId(),item.id(),version,"ACTIVE",sealed.payload(),sealed.keyVersion(),sealed.nonce(),sealed.tag(),sealed.hmac(),policy.id(),policy.versionId(),decision,item.currentVersionId(),expires,item.revision()+1,item.grantEpoch(),item.sourceEpoch(),item.deletionEpoch());
  requireOne(mapper.insertPreferenceVersion(row));
  byte[] source=MemoryMapper.identity(java.util.UUID.randomUUID().toString());
  requireOne(mapper.insertPreferenceSource(item.tenantId(),source,decision,version,expires));
  requireOne(mapper.insertPreferenceDependency(item.tenantId(),source,item.id(),version));
  requireOne(mapper.compareAndSetCurrent(item.tenantId(),item.id(),item.revision(),version,"LIVE"));return row;
 }
 public static void requireOne(int rows){if(rows!=1)throw new MemoryException("MEMORY_REVISION_CONFLICT");}
}

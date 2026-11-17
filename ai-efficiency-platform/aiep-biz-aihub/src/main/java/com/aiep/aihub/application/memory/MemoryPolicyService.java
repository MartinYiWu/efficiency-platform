package com.aiep.aihub.application.memory;
import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.repository.memory.MemoryMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.*;
import org.springframework.stereotype.Service;

/** 只消费已发布不可变策略；固定目录是最大支持面，不代表默认启用。 */
@Service
public class MemoryPolicyService {
 private static final Map<String,Set<String>> SUPPORTED=Map.of("response.language",Set.of("zh-CN","en-US"),"response.detail_level",Set.of("concise","standard","detailed"),"response.format",Set.of("prose","bullets","table"));
 private final MemoryMapper mapper;
 public MemoryPolicyService(MemoryMapper mapper){this.mapper=mapper;}
 public Published require(MemoryScopeDTO scope,String field,String value){
  if(!SUPPORTED.containsKey(field))throw new MemoryException("FEATURE_DISABLED");
  var row=mapper.findPublishedPolicy(MemoryMapper.identity(scope.tenantId()),scope.domain());
  if(row==null||!"memory-policy/1".equals(row.schemaVersion()))throw new MemoryException("FEATURE_DISABLED");
  try {
   var root=new ObjectMapper().readTree(row.policyJson());var node=root.path("fields").path(field);
   if(!node.path("enabled").asBoolean(false)||!node.path("values").isArray())throw new MemoryException("FEATURE_DISABLED");
   Set<String> values=new HashSet<>();node.path("values").forEach(n->values.add(n.asText()));
   if(values.isEmpty()||!SUPPORTED.get(field).containsAll(values))throw new MemoryException("FEATURE_DISABLED");
   long retention=node.path("retentionSeconds").asLong(0),source=node.path("sourceRetentionSeconds").asLong(0);
   if(retention<=0||source<=0||retention>31536000||source>31536000)throw new MemoryException("FEATURE_DISABLED");
   if(value!=null&&!values.contains(value))throw new MemoryException("MEMORY_VALUE_INVALID");
   return new Published(row.id(),row.versionId(),Math.min(retention,source));
  }catch(MemoryException failure){throw failure;}catch(Exception failure){throw new MemoryException("FEATURE_DISABLED");}
 }
 public record Published(byte[] id,byte[] versionId,long retentionSeconds){}
 /** 仅不可变原策略可以证明从未配置索引；当前开关和查无记录都不是清理证明。 */
 public static void requireUnprovisionedIndex(JsonNode root){
  var artifacts=root==null?null:root.get("artifacts");
  if(artifacts==null||!artifacts.isObject())throw new MemoryException("FEATURE_DISABLED");
  var names=new HashSet<String>();artifacts.fieldNames().forEachRemaining(names::add);
  if(!names.equals(Set.of("schema_version","index_mode","index_backends"))
    ||!artifacts.path("schema_version").isTextual()||!"memory-artifacts/1".equals(artifacts.path("schema_version").textValue())
    ||!artifacts.path("index_mode").isTextual()||!"NOT_PROVISIONED".equals(artifacts.path("index_mode").textValue())
    ||!artifacts.path("index_backends").isArray()||!artifacts.path("index_backends").isEmpty())throw new MemoryException("FEATURE_DISABLED");
 }
 public static void requireArtifactPolicy(MemoryMapper.PolicyPO row){
  if(row==null||!"memory-policy/1".equals(row.schemaVersion()))throw new MemoryException("FEATURE_DISABLED");
  try{requireUnprovisionedIndex(new ObjectMapper().readTree(row.policyJson()));}
  catch(MemoryException failure){throw failure;}catch(Exception failure){throw new MemoryException("FEATURE_DISABLED");}
 }
 public void requireVersionArtifacts(byte[] tenant,List<MemoryMapper.VersionIdentityPO> versions){
  if(versions.isEmpty())return;
  var expected=new HashSet<String>();
  for(var version:versions)expected.add(versionKey(version.itemId(),version.versionId()));
  var actual=new HashSet<String>();
  for(var row:mapper.listVersionPolicies(tenant,versions)){
   requireArtifactPolicy(new MemoryMapper.PolicyPO(row.policyId(),row.policyVersionId(),row.policyJson(),null,row.schemaVersion()));
   if(!actual.add(versionKey(row.itemId(),row.versionId())))throw new MemoryException("FEATURE_DISABLED");
  }
  if(!actual.equals(expected))throw new MemoryException("FEATURE_DISABLED");
 }
 private static String versionKey(byte[] item,byte[] version){return Base64.getEncoder().encodeToString(item)+":"+Base64.getEncoder().encodeToString(version);}
}

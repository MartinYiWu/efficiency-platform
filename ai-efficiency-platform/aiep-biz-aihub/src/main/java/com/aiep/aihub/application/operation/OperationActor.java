package com.aiep.aihub.application.operation;
/** sessionRef仅供服务端异步重新授权，不序列化到外部Agent。 */
public record OperationActor(String tenantId,String userId,@com.fasterxml.jackson.annotation.JsonIgnore String sessionRef) {
 public OperationActor(String tenantId,String userId){this(tenantId,userId,null);}
 public OperationActor {
  for(String id:new String[]{tenantId,userId})
   if(id==null||id.isBlank()||id.codePointCount(0,id.length())>128
    ||id.codePoints().anyMatch(cp->cp>=0xd800&&cp<=0xdfff)
    ||id.getBytes(java.nio.charset.StandardCharsets.UTF_8).length>512)
    throw new IllegalArgumentException("MEMORY_ACTOR_INVALID");
 }
}

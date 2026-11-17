package com.aiep.aihub.memory;

import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.facade.memory.DefaultMemoryFacade;
import com.aiep.aihub.repository.memory.*;
import com.aiep.aihub.web.memory.*;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.identity.facade.DatabaseIdentityFacade;
import com.aiep.identity.repository.IdentitySessionMapper;
import com.aiep.platformcore.config.TraceIdFilter;
import com.baomidou.mybatisplus.extension.spring.MybatisSqlSessionFactoryBean;
import com.baomidou.mybatisplus.autoconfigure.MybatisPlusAutoConfiguration;
import java.net.URI;
import java.net.http.*;
import java.sql.*;
import java.util.*;
import java.util.concurrent.*;
import javax.sql.DataSource;
import org.apache.ibatis.session.SqlSessionFactory;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.boot.*;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.annotation.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.*;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import static com.aiep.aihub.memory.MemoryPreferenceIntegrationTest.*;
import static org.junit.jupiter.api.Assertions.*;

/** 隔离本机MySQL+生产HTTP/认证/Mapper；仅外部清理端口为显式fixture，不等于真实Agent/thread删除。 */
@EnabledIfSystemProperty(named="memory.integration.enabled",matches="true")
class MemoryForgetIntegrationTest {
 static final DependencyRaceGate DEPENDENCY_RACE=new DependencyRaceGate();
 @Configuration(proxyBeanMethods=false)
 @EnableAutoConfiguration(exclude={DataSourceAutoConfiguration.class,MybatisPlusAutoConfiguration.class},excludeName={"org.redisson.spring.starter.RedissonAutoConfigurationV2","org.springframework.boot.autoconfigure.data.redis.RedisAutoConfiguration","org.springframework.boot.autoconfigure.data.redis.RedisRepositoriesAutoConfiguration"})
 @EnableTransactionManagement
 @Import({ConversationScopeResolver.class,MemoryScopePolicy.class,MemorySessionBindingService.class,MemoryPolicyService.class,MemoryVersionService.class,MemoryPreferenceService.class,DefaultMemoryFacade.class,MemoryActorResolver.class,MemoryController.class,MemoryExceptionHandler.class,TraceIdFilter.class,MemoryForgetService.class,MemorySuppressionService.class,MemoryDeletionService.class,MemorySourceInvalidationService.class,MemoryDeletionController.class,StorageDiagnosticHandler.class})
 static class ITConfiguration {
  @Bean DataSource dataSource(){return new DriverManagerDataSource(required("MEMORY_IT_MYSQL_JDBC_URL"),required("MEMORY_IT_MYSQL_USER"),required("MEMORY_IT_MYSQL_PASSWORD"));}
  @Bean PlatformTransactionManager transactionManager(DataSource ds){return new DataSourceTransactionManager(ds);}
  @Bean SqlSessionFactory sqlSessionFactory(DataSource ds)throws Exception{var factory=new MybatisSqlSessionFactoryBean();factory.setDataSource(ds);factory.setMapperLocations(new ClassPathResource("mapper/memory/MemoryMapper.xml"),new ClassPathResource("mapper/memory/MemoryForgetMapper.xml"),new ClassPathResource("mapper/identity/IdentitySessionMapper.xml"));var conf=new com.baomidou.mybatisplus.core.MybatisConfiguration();conf.setMapUnderscoreToCamelCase(true);factory.setConfiguration(conf);factory.setPlugins(DEPENDENCY_RACE);return factory.getObject();}
  @Bean MemoryMapper memoryMapper(SqlSessionFactory factory){return new SqlSessionTemplate(factory).getMapper(MemoryMapper.class);}
  @Bean MemoryForgetMapper forgetMapper(SqlSessionFactory factory){return new SqlSessionTemplate(factory).getMapper(MemoryForgetMapper.class);}
  @Bean IdentitySessionMapper identityMapper(SqlSessionFactory factory){return new SqlSessionTemplate(factory).getMapper(IdentitySessionMapper.class);}
  @Bean IdentityFacade identity(IdentitySessionMapper mapper){return new DatabaseIdentityFacade(mapper);}
  @Bean MemoryValueCodec codec(){byte[] key=random(32),mac=random(32);return new MemoryValueCodec("it","{\"it\":\""+Base64.getEncoder().encodeToString(key)+"\"}",Base64.getEncoder().encodeToString(mac));}
  @Bean TestCleanupAck cleanup(){return new TestCleanupAck();}
 }
 @org.springframework.web.bind.annotation.RestControllerAdvice(assignableTypes=MemoryDeletionController.class)
 static class StorageDiagnosticHandler extends MemoryDeletionExceptionHandler {
  @Override @org.springframework.web.bind.annotation.ExceptionHandler(org.springframework.dao.DataAccessException.class)
  public org.springframework.http.ResponseEntity<com.aiep.platformcore.api.ApiResponse<Void>> storage(org.springframework.dao.DataAccessException error){
   // 仅测试诊断类型与厂商码；异常message可能携带SQL/绑定值，禁止打印或附加完整stacktrace。
   Throwable cause=error;for(int depth=0;cause!=null&&depth<16;depth++,cause=cause.getCause()){
    String code="none",state="none";
    if(cause instanceof SQLException sql){code=Integer.toString(sql.getErrorCode());String raw=sql.getSQLState();state=raw!=null&&raw.matches("[A-Za-z0-9]{5}")?raw:"unknown";}
    System.err.println("D15_STORAGE_DIAGNOSTIC class="+cause.getClass().getName()+" vendorCode="+code+" sqlState="+state);
   }
   return super.storage(error);
  }
 }
 static class TestCleanupAck implements MemoryDeletionService.RevocationAckPort {
  volatile boolean allConfirmed;
  public MemoryDeletionService.Acknowledgement acknowledge(MemoryDeletionService.RevocationRequest request){
   if(!allConfirmed)return MemoryDeletionService.Acknowledgement.pending(request.eventId(),request.deletionEpoch());
   var receipts=new EnumMap<MemoryDeletionService.CleanupTarget,String>(MemoryDeletionService.CleanupTarget.class);
   for(var target:MemoryDeletionService.CleanupTarget.values())if(target!=MemoryDeletionService.CleanupTarget.VERSION_PAYLOAD)receipts.put(target,"EXPLICIT_TEST_EXTERNAL_ACK_"+target.name());
   return new MemoryDeletionService.Acknowledgement(request.eventId(),request.deletionEpoch(),receipts);
  }
 }
 @Test void realForgetPendingAtomicScrubNewReauthorizationAndScopeIsolation()throws Exception{
  var ds=checkedDataSource();try(var c=ds.getConnection()){
   sourceTable(c,"V1.0.0__operation_assistant_mvp.sql","ai_operation_conversation");sourceTable(c,"V1.1.0__customer_service_knowledge_aihub.sql","ai_customer_service_conversation");sourceTable(c,"V1.2.3__hr_execution_identity_and_sources.sql","id_hr_session");sourceTable(c,"V1.2.3__hr_execution_identity_and_sources.sql","id_hr_grant");seed(c);
  }
  var app=new SpringApplication(ITConfiguration.class);app.setDefaultProperties(Map.of("spring.config.location","optional:classpath:/memory-it-no-shared-config/","server.address","127.0.0.1","server.port","0","spring.main.banner-mode","off","logging.level.root","WARN","spring.jmx.enabled","false"));
  try(var context=(ServletWebServerApplicationContext)app.run("--spring.config.location=optional:classpath:/memory-it-no-shared-config/","--server.address=127.0.0.1","--server.port=0")){
   base="http://127.0.0.1:"+context.getWebServer().getPort()+"/api/aihub";String token=TOKENS.get("t1:u1");
   var save=new LinkedHashMap<String,Object>(Map.of("topAgent","operations","fieldKey","response.language","value","zh-CN","expectedRevision",0,"idempotencyKey","d15-save"));
   var saved=post("/memories",token,JSON.writeValueAsString(save),200).path("data");String id=saved.path("id").asText(),old=saved.path("versionId").asText();
   get("/memories/"+id+"?topAgent=operations",token,200);
   var deletion=new LinkedHashMap<String,Object>(Map.of("topAgent","operations","itemId",id,"expectedRevision",1,"idempotencyKey","d15-forget"));
   var wrongOwner=rawPost("/memory-deletions",TOKENS.get("t1:u2"),JSON.writeValueAsString(deletion));assertEquals(404,wrongOwner.statusCode());
   var foreignAgent=new LinkedHashMap<>(deletion);foreignAgent.put("topAgent","hr");post("/memory-deletions",token,JSON.writeValueAsString(foreignAgent),404);
   post("/memory-deletions",TOKENS.get("t2:u1"),JSON.writeValueAsString(deletion),404);
   var forgotten=post("/memory-deletions",token,JSON.writeValueAsString(deletion),200).path("data");String job=forgotten.path("jobId").asText(),supp=forgotten.path("suppressionId").asText();assertEquals("DELETE_PENDING",forgotten.path("status").asText());assertEquals(0,forgotten.path("completedTargets").asInt());
   get("/memories/"+id+"?topAgent=operations",token,404);assertEquals(0,get("/memories?topAgent=operations",token,200).path("data").path("total").asInt());
   assertEquals(job,post("/memory-deletions",token,JSON.writeValueAsString(deletion),200).path("data").path("jobId").asText());
   var duplicate=new LinkedHashMap<>(deletion);duplicate.put("idempotencyKey","d15-different-key");assertEquals(job,post("/memory-deletions",token,JSON.writeValueAsString(duplicate),200).path("data").path("jobId").asText());
   save.put("idempotencyKey","old-chat-replayed");post("/memories",token,JSON.writeValueAsString(save),422);
   var reauthorize=new LinkedHashMap<String,Object>(Map.of("topAgent","operations","itemId",id,"fieldKey","response.language","value","en-US","expectedRevision",2,"expected_suppression_revision",1,"idempotencyKey","d15-reauthorize","confirmation","ALLOW_REMEMBER"));
   post("/memory-suppressions/"+supp+"/reauthorizations",token,JSON.writeValueAsString(reauthorize),409);
   context.getBean(MemoryDeletionService.class).compensate("t1",job);
   var pending=get("/memory-deletions/"+job+"?topAgent=operations",token,200).path("data");assertEquals("DELETE_PENDING",pending.path("status").asText());assertEquals("BLOCKED",pending.path("jobStatus").asText());assertEquals(0,pending.path("completedTargets").asInt());
   assertBody(ds,id,old,false);
   context.getBean(TestCleanupAck.class).allConfirmed=true;context.getBean(MemoryDeletionService.class).compensate("t1",job);
   var done=get("/memory-deletions/"+job+"?topAgent=operations",token,200).path("data");assertEquals("DELETED",done.path("status").asText());assertEquals("SUCCEEDED",done.path("jobStatus").asText());assertEquals(6,done.path("completedTargets").asInt());assertBody(ds,id,old,true);
   reauthorize.put("expectedRevision",done.path("revision").asLong());
   var bad=new LinkedHashMap<>(reauthorize);bad.put("expected_suppression_revision",0);post("/memory-suppressions/"+supp+"/reauthorizations",token,JSON.writeValueAsString(bad),400);
   var active=post("/memory-suppressions/"+supp+"/reauthorizations",token,JSON.writeValueAsString(reauthorize),200).path("data");assertNotEquals(old,active.path("versionId").asText());assertEquals("ACTIVE",active.path("status").asText());assertBody(ds,id,old,true);
   var historicalJob=get("/memory-deletions/"+job+"?topAgent=operations",token,200).path("data");assertEquals("LIVE",historicalJob.path("status").asText());assertEquals("SUCCEEDED",historicalJob.path("jobStatus").asText());assertEquals(active.path("revision"),historicalJob.path("revision"));assertEquals(forgotten.path("deletionEpoch"),historicalJob.path("deletionEpoch"));assertEquals(forgotten.path("suppressionRevision"),historicalJob.path("suppressionRevision"));
   var repeatedGrant=new LinkedHashMap<>(reauthorize);repeatedGrant.put("expectedRevision",active.path("revision").asLong());repeatedGrant.put("idempotencyKey","d15-old-job-cannot-grant-again");post("/memory-suppressions/"+supp+"/reauthorizations",token,JSON.writeValueAsString(repeatedGrant),409);
   var detail=get("/memories/"+id+"?topAgent=operations",token,200).path("data");assertEquals("en-US",detail.path("preference").path("value").asText());assertEquals(1,detail.path("history").size());
   assertEquals(active.path("versionId"),post("/memory-suppressions/"+supp+"/reauthorizations",token,JSON.writeValueAsString(reauthorize),200).path("data").path("versionId"));
   try(var c=ds.getConnection();var ps=c.prepareStatement("SELECT COUNT(*) FROM ai_memory_suppression WHERE tenant_id=? AND suppression_kind='SOURCE' AND active=TRUE")){ps.setBytes(1,MemoryMapper.identity("t1"));try(var r=ps.executeQuery()){assertTrue(r.next());assertEquals(1,r.getInt(1));}}
   var corrected=post("/memories/"+id+"/corrections",token,JSON.writeValueAsString(Map.of("topAgent","operations","fieldKey","response.language","value","zh-CN","expectedRevision",active.path("revision").asLong(),"idempotencyKey","d15-correct-after-reauthorization")),200).path("data");
   assertEquals(active.path("revision").asLong()+1,corrected.path("revision").asLong());assertNotEquals(active.path("versionId"),corrected.path("versionId"));assertBody(ds,id,old,true);
   assertCorrectionEpochs(ds,id,corrected.path("versionId").asText());
   var afterCorrection=get("/memories/"+id+"?topAgent=operations",token,200).path("data");assertEquals("zh-CN",afterCorrection.path("preference").path("value").asText());assertEquals(corrected.path("versionId"),afterCorrection.path("preference").path("versionId"));assertEquals(2,afterCorrection.path("history").size());assertEquals("SUPERSEDED",afterCorrection.path("history").get(1).path("status").asText());assertEquals("en-US",afterCorrection.path("history").get(1).path("value").asText());
   raceSaveForget(token,id,corrected.path("revision").asLong());
   sourceCascadeUsesRealOwnerAndOnlyActualSourceDependents(context,ds,token);
   concurrentSourceWriterMustBeIncludedInPersistedCleanup(ds);
  }
 }
 static void assertCorrectionEpochs(DataSource ds,String item,String version)throws Exception{
  try(var c=ds.getConnection();var ps=c.prepareStatement("SELECT i.grant_epoch,i.source_epoch,i.deletion_epoch,v.grant_epoch,v.source_epoch,v.deletion_epoch,s.grant_epoch,s.source_epoch,s.deletion_epoch,d.grant_epoch,d.source_epoch,d.deletion_epoch FROM ai_memory_item i JOIN ai_memory_version v ON v.tenant_id=i.tenant_id AND v.item_id=i.id AND v.id=i.current_version_id JOIN ai_memory_dependency d ON d.tenant_id=v.tenant_id AND d.target_type='MEMORY_VERSION' AND d.target_id=v.item_id AND d.target_version=v.id JOIN ai_memory_source s ON s.tenant_id=d.tenant_id AND s.id=d.source_id AND s.source_object_ref=v.decision_id AND s.source_version=v.id WHERE i.tenant_id=? AND i.id=? AND v.id=?")){
   ps.setBytes(1,MemoryMapper.identity("t1"));ps.setBytes(2,MemoryMapper.identity(item));ps.setBytes(3,MemoryMapper.identity(version));
   try(var row=ps.executeQuery()){assertTrue(row.next());for(int n=1;n<=3;n++){assertTrue(row.getLong(n)>0);assertEquals(row.getLong(n),row.getLong(n+3));}assertEquals(0,row.getLong(7));assertEquals(1,row.getLong(8));assertEquals(0,row.getLong(9));assertEquals(0,row.getLong(10));assertEquals(1,row.getLong(11));assertEquals(0,row.getLong(12));assertFalse(row.next());}
  }
 }
 @org.apache.ibatis.plugin.Intercepts(@org.apache.ibatis.plugin.Signature(type=org.apache.ibatis.executor.Executor.class,method="query",args={org.apache.ibatis.mapping.MappedStatement.class,Object.class,org.apache.ibatis.session.RowBounds.class,org.apache.ibatis.session.ResultHandler.class}))
 static class DependencyRaceGate implements org.apache.ibatis.plugin.Interceptor {
  volatile byte[] item;volatile long forgetConnection;volatile CountDownLatch firstSourceRead;final java.util.concurrent.atomic.AtomicBoolean armed=new java.util.concurrent.atomic.AtomicBoolean();
  public Object intercept(org.apache.ibatis.plugin.Invocation invocation)throws Throwable{
   Object result=invocation.proceed();var statement=(org.apache.ibatis.mapping.MappedStatement)invocation.getArgs()[0];
   if(statement.getId().endsWith(".listItemSources")&&invocation.getArgs()[1] instanceof Map<?,?> parameters&&Arrays.equals(item,(byte[])parameters.get("item"))&&armed.compareAndSet(true,false)){
    assertFalse(((List<?>)result).isEmpty());var executor=(org.apache.ibatis.executor.Executor)invocation.getTarget();var connection=executor.getTransaction().getConnection();
    assertEquals(Connection.TRANSACTION_REPEATABLE_READ,connection.getTransactionIsolation());
    try(var query=connection.createStatement();var row=query.executeQuery("SELECT CONNECTION_ID()")){assertTrue(row.next());forgetConnection=row.getLong(1);}
    firstSourceRead.countDown();
   }
   return result;
  }
 }
 static void concurrentSourceWriterMustBeIncludedInPersistedCleanup(DataSource ds)throws Exception{
  String token=TOKENS.get("t2:u2");var saved=post("/memories",token,JSON.writeValueAsString(Map.of("topAgent","operations","fieldKey","response.detail_level","value","concise","expectedRevision",0,"idempotencyKey","d15-rr-save")),200).path("data");
  String item=saved.path("id").asText(),message="d15-rr-actual-message";byte[] tenant=MemoryMapper.identity("t2"),source;
  try(var writer=ds.getConnection()){
   writer.setAutoCommit(false);writer.setTransactionIsolation(Connection.TRANSACTION_REPEATABLE_READ);long writerId;
   try(var q=writer.createStatement();var row=q.executeQuery("SELECT CONNECTION_ID()")){assertTrue(row.next());writerId=row.getLong(1);}
   try(var q=writer.prepareStatement("SELECT source_id FROM ai_memory_dependency WHERE tenant_id=? AND target_type='MEMORY_VERSION' AND target_id=? AND target_version=?")){q.setBytes(1,tenant);q.setBytes(2,MemoryMapper.identity(item));q.setBytes(3,MemoryMapper.identity(saved.path("versionId").asText()));try(var row=q.executeQuery()){assertTrue(row.next());source=row.getBytes(1);}}
   try(var q=writer.prepareStatement("SELECT id FROM ai_memory_source WHERE tenant_id=? AND id=? FOR UPDATE")){q.setBytes(1,tenant);q.setBytes(2,source);try(var row=q.executeQuery()){assertTrue(row.next());}}
   try(var q=writer.prepareStatement("INSERT INTO ai_memory_dependency(tenant_id,source_id,target_type,target_id,target_version,source_epoch) VALUES(?,?,'MESSAGE',?,?,1)")){q.setBytes(1,tenant);q.setBytes(2,source);q.setBytes(3,MemoryMapper.identity(message));q.setBytes(4,MemoryMapper.identity("v1"));assertEquals(1,q.executeUpdate());}
   DEPENDENCY_RACE.item=MemoryMapper.identity(item);DEPENDENCY_RACE.firstSourceRead=new CountDownLatch(1);DEPENDENCY_RACE.armed.set(true);
   var pool=Executors.newSingleThreadExecutor();try{
    String deletion=JSON.writeValueAsString(Map.of("topAgent","operations","itemId",item,"expectedRevision",1,"idempotencyKey","d15-rr-forget"));var future=pool.submit(()->rawPost("/memory-deletions",token,deletion));
    assertTrue(DEPENDENCY_RACE.firstSourceRead.await(10,TimeUnit.SECONDS));assertNotEquals(writerId,DEPENDENCY_RACE.forgetConnection);
    boolean waiting=false;long stop=System.nanoTime()+TimeUnit.SECONDS.toNanos(10);
    while(System.nanoTime()<stop&&!waiting){try(var q=writer.prepareStatement("SELECT COUNT(*) FROM information_schema.innodb_trx WHERE trx_mysql_thread_id=? AND trx_state='LOCK WAIT'")){q.setLong(1,DEPENDENCY_RACE.forgetConnection);try(var row=q.executeQuery()){assertTrue(row.next());waiting=row.getInt(1)==1;}}if(!waiting)java.util.concurrent.locks.LockSupport.parkNanos(TimeUnit.MILLISECONDS.toNanos(10));}
    assertTrue(waiting,"forget must wait for the actual source writer lock");assertFalse(future.isDone());writer.commit();
    var response=future.get(20,TimeUnit.SECONDS);assertEquals(200,response.statusCode());String job=checked(response).path("data").path("jobId").asText();
    try(var read=ds.getConnection();var q=read.prepareStatement("SELECT receipts FROM ai_memory_deletion_job WHERE tenant_id=? AND id=?")){q.setBytes(1,tenant);q.setBytes(2,MemoryMapper.identity(job));try(var row=q.executeQuery()){assertTrue(row.next());var dependencies=JSON.readTree(row.getString(1)).path("dependencies");boolean included=false;for(var edge:dependencies)if("MESSAGE".equals(edge.path("targetType").asText())&&Arrays.equals(MemoryMapper.identity(message),edge.path("targetId").binaryValue()))included=true;assertTrue(included,"cleanup job must include the actual dependency committed by the source lock holder");}}
    System.out.println("D15 actual dependency race: distinctConnections=true, sourceLockWait=true, lateCommittedDependencyIncluded=true");
   }finally{DEPENDENCY_RACE.item=null;DEPENDENCY_RACE.armed.set(false);writer.rollback();pool.shutdownNow();}
  }
 }
 static void sourceCascadeUsesRealOwnerAndOnlyActualSourceDependents(ServletWebServerApplicationContext context,DataSource ds,String token)throws Exception{
  String other=TOKENS.get("t1:u2");
  var sourceItem=post("/memories",token,JSON.writeValueAsString(Map.of("topAgent","operations","fieldKey","response.format","value","prose","expectedRevision",0,"idempotencyKey","d15-source-owner")),200).path("data");
  var derived=post("/memories",other,JSON.writeValueAsString(Map.of("topAgent","operations","fieldKey","response.format","value","table","expectedRevision",0,"idempotencyKey","d15-source-derived")),200).path("data");
  var unrelated=post("/memories",other,JSON.writeValueAsString(Map.of("topAgent","operations","fieldKey","response.language","value","zh-CN","expectedRevision",0,"idempotencyKey","d15-source-unrelated")),200).path("data");
  byte[] source;
  try(var c=ds.getConnection()){
   try(var ps=c.prepareStatement("SELECT source_id FROM ai_memory_dependency WHERE tenant_id=? AND target_type='MEMORY_VERSION' AND target_id=? AND target_version=?")){ps.setBytes(1,MemoryMapper.identity("t1"));ps.setBytes(2,MemoryMapper.identity(sourceItem.path("id").asText()));ps.setBytes(3,MemoryMapper.identity(sourceItem.path("versionId").asText()));try(var r=ps.executeQuery()){assertTrue(r.next());source=r.getBytes(1);}}
   // 模拟已经登记的实际传递输入边，不mock业务Mapper或来源授权。
   try(var ps=c.prepareStatement("INSERT INTO ai_memory_dependency(tenant_id,source_id,target_type,target_id,target_version,source_epoch) VALUES(?,?,'MEMORY_VERSION',?,?,1)")){ps.setBytes(1,MemoryMapper.identity("t1"));ps.setBytes(2,source);ps.setBytes(3,MemoryMapper.identity(derived.path("id").asText()));ps.setBytes(4,MemoryMapper.identity(derived.path("versionId").asText()));assertEquals(1,ps.executeUpdate());}
  }
  var identity=context.getBean(IdentityFacade.class);var actor=identity.authenticate(token).orElseThrow();var wrong=identity.authenticate(other).orElseThrow();var service=context.getBean(MemorySourceInvalidationService.class);
  var scope=new com.aiep.aihub.api.memory.MemoryScopeDTO("t1","u1","operations","operations","TASK_ONLY",null);
  var wrongScope=new com.aiep.aihub.api.memory.MemoryScopeDTO("t1","u2","operations","operations","TASK_ONLY",null);
  String sourceId=new String(source,java.nio.charset.StandardCharsets.UTF_8);
  assertEquals("MEMORY_NOT_FOUND",assertThrows(com.aiep.aihub.api.memory.MemoryContracts.MemoryException.class,()->service.invalidateOwnedSource(wrong,wrongScope,sourceId,1)).code());
  var revoked=service.invalidateOwnedSource(actor,scope,sourceId,1);assertEquals(2,revoked.sourceEpoch());assertEquals(2,revoked.affectedTargets());
  assertEquals(2,service.invalidateOwnedSource(actor,scope,sourceId,1).sourceEpoch());
  get("/memories/"+sourceItem.path("id").asText()+"?topAgent=operations",token,404);get("/memories/"+derived.path("id").asText()+"?topAgent=operations",other,404);
  get("/memories/"+unrelated.path("id").asText()+"?topAgent=operations",other,200);
  assertEquals("FEATURE_DISABLED",assertThrows(com.aiep.aihub.api.memory.MemoryContracts.MemoryException.class,()->service.principalLeftProject(actor,scope)).code());
  assertEquals("FEATURE_DISABLED",assertThrows(com.aiep.aihub.api.memory.MemoryContracts.MemoryException.class,()->service.withdrawSharing(actor,scope)).code());
  get("/memories/"+unrelated.path("id").asText()+"?topAgent=operations",other,200);
  try(var c=ds.getConnection();var r=c.createStatement().executeQuery("SELECT COUNT(*) FROM ai_memory_suppression WHERE tenant_id=_binary't1' AND suppression_kind='FIELD' AND field_key='response.format'")){assertTrue(r.next());assertEquals(0,r.getInt(1));}
 }
 static void assertBody(DataSource ds,String item,String version,boolean scrubbed)throws Exception{try(var c=ds.getConnection();var ps=c.prepareStatement("SELECT status,encrypted_payload,nonce,auth_tag,content_hmac,scrubbed_at FROM ai_memory_version WHERE tenant_id=? AND item_id=? AND id=?")){ps.setBytes(1,MemoryMapper.identity("t1"));ps.setBytes(2,MemoryMapper.identity(item));ps.setBytes(3,MemoryMapper.identity(version));try(var r=ps.executeQuery()){assertTrue(r.next());assertEquals(scrubbed?"DELETED":"REVOKED",r.getString(1));for(int n=2;n<=5;n++){if(scrubbed)assertNull(r.getBytes(n));else assertNotNull(r.getBytes(n));}assertEquals(scrubbed,r.getTimestamp(6)!=null);}}}
 static void raceSaveForget(String token,String item,long revision)throws Exception{
  var gate=new CyclicBarrier(2);var pool=Executors.newFixedThreadPool(2);try{
   String correction=JSON.writeValueAsString(Map.of("topAgent","operations","fieldKey","response.language","value","en-US","expectedRevision",revision,"idempotencyKey","d15-race-save"));
   String deletion=JSON.writeValueAsString(Map.of("topAgent","operations","itemId",item,"expectedRevision",revision,"idempotencyKey","d15-race-forget"));
   var first=pool.submit(()->{gate.await(10,TimeUnit.SECONDS);return rawPost("/memories/"+item+"/corrections",token,correction);});var second=pool.submit(()->{gate.await(10,TimeUnit.SECONDS);return rawPost("/memory-deletions",token,deletion);});
   var left=first.get(30,TimeUnit.SECONDS);var right=second.get(30,TimeUnit.SECONDS);assertTrue(Set.of(200,409,422,503).contains(left.statusCode()));assertTrue(Set.of(200,409,503).contains(right.statusCode()));
   // 若更正先提交，以最新revision显式重试忘记；最终删除epoch必须阻断全部旧确认。
   if(right.statusCode()!=200){var current=get("/memories/"+item+"?topAgent=operations",token,200).path("data").path("preference");String retryDeletion=JSON.writeValueAsString(Map.of("topAgent","operations","itemId",item,"expectedRevision",current.path("revision").asLong(),"idempotencyKey","d15-race-forget-retry"));post("/memory-deletions",token,retryDeletion,200);}
   get("/memories/"+item+"?topAgent=operations",token,404);post("/memories/"+item+"/corrections",token,correction.replace("d15-race-save","d15-late-save"),422);
  }finally{pool.shutdownNow();}
 }
}

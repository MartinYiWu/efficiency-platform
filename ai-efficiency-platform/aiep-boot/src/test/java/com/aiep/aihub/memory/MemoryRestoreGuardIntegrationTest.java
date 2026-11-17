package com.aiep.aihub.memory;

import com.aiep.aihub.api.memory.MemoryContracts.*;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.repository.memory.*;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.identity.facade.DatabaseIdentityFacade;
import com.aiep.identity.repository.IdentitySessionMapper;
import com.baomidou.mybatisplus.autoconfigure.MybatisPlusAutoConfiguration;
import com.baomidou.mybatisplus.extension.spring.MybatisSqlSessionFactoryBean;
import java.sql.*;
import java.time.Instant;
import java.util.*;
import javax.sql.DataSource;
import org.apache.ibatis.session.SqlSessionFactory;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.junit.jupiter.api.function.Executable;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.boot.*;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.annotation.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.*;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import static com.aiep.aihub.memory.MemoryPreferenceIntegrationTest.*;
import static org.junit.jupiter.api.Assertions.*;

/** 只由root隔离MySQL runner执行；模拟删除清单先恢复、旧ACTIVE正文随后可见，无外部调用。 */
@EnabledIfSystemProperty(named="memory.integration.enabled",matches="true")
class MemoryRestoreGuardIntegrationTest {
 @Configuration(proxyBeanMethods=false)
 @EnableAutoConfiguration(exclude={DataSourceAutoConfiguration.class,MybatisPlusAutoConfiguration.class},excludeName={"org.redisson.spring.starter.RedissonAutoConfigurationV2","org.springframework.boot.autoconfigure.data.redis.RedisAutoConfiguration","org.springframework.boot.autoconfigure.data.redis.RedisRepositoriesAutoConfiguration"})
 @EnableTransactionManagement
 @Import({ConversationScopeResolver.class,MemoryScopePolicy.class,MemorySessionBindingService.class,MemoryPolicyService.class,
  MemoryVersionService.class,MemoryPreferenceService.class,MemoryPacketService.class,MemoryDependencyService.class,MemoryHistoryProjection.class,
  MemoryForgetService.class,MemorySuppressionService.class,MemoryDeletionService.class,com.aiep.aihub.web.memory.MemoryActorResolver.class})
 static class ITConfiguration {
  @Bean DataSource dataSource(){return new DriverManagerDataSource(required("MEMORY_IT_MYSQL_JDBC_URL"),required("MEMORY_IT_MYSQL_USER"),required("MEMORY_IT_MYSQL_PASSWORD"));}
  @Bean PlatformTransactionManager transactionManager(DataSource ds){return new DataSourceTransactionManager(ds);}
  @Bean SqlSessionFactory sqlSessionFactory(DataSource ds)throws Exception{
   var factory=new MybatisSqlSessionFactoryBean();factory.setDataSource(ds);
   factory.setMapperLocations(new ClassPathResource("mapper/memory/MemoryMapper.xml"),new ClassPathResource("mapper/memory/MemoryPacketMapper.xml"),new ClassPathResource("mapper/memory/MemoryForgetMapper.xml"),new ClassPathResource("mapper/identity/IdentitySessionMapper.xml"));
   var conf=new com.baomidou.mybatisplus.core.MybatisConfiguration();conf.setMapUnderscoreToCamelCase(true);factory.setConfiguration(conf);return factory.getObject();
  }
  @Bean MemoryMapper memories(SqlSessionFactory f){return new SqlSessionTemplate(f).getMapper(MemoryMapper.class);}
  @Bean MemoryPacketMapper packets(SqlSessionFactory f){return new SqlSessionTemplate(f).getMapper(MemoryPacketMapper.class);}
  @Bean MemoryForgetMapper forgetMapper(SqlSessionFactory f){return new SqlSessionTemplate(f).getMapper(MemoryForgetMapper.class);}
  @Bean IdentitySessionMapper identityMapper(SqlSessionFactory f){return new SqlSessionTemplate(f).getMapper(IdentitySessionMapper.class);}
  @Bean IdentityFacade identity(IdentitySessionMapper mapper){return new DatabaseIdentityFacade(mapper);}
  @Bean MemoryValueCodec codec(){return new MemoryValueCodec("it","{\"it\":\""+Base64.getEncoder().encodeToString(random(32))+"\"}",Base64.getEncoder().encodeToString(random(32)));}
  // 仅构造已经完成的本地重授权前置状态；不是外部清理实际完成的证据。
  @Bean MemoryForgetIntegrationTest.TestCleanupAck cleanup(){return new MemoryForgetIntegrationTest.TestCleanupAck();}
 }

 @Test void newerDeletionManifestMustWinOverRestoredActiveBodiesAndAllowExplicitNewGrant()throws Exception{
  var url=java.net.URI.create(required("MEMORY_IT_MYSQL_JDBC_URL").substring(5));
  assertEquals("127.0.0.1",url.getHost());assertNull(url.getUserInfo());assertTrue(url.getPath().matches("/aiep_memory_it_[0-9]{8}_[0-9a-f]{10}"));
  var ds=new DriverManagerDataSource(required("MEMORY_IT_MYSQL_JDBC_URL"),required("MEMORY_IT_MYSQL_USER"),required("MEMORY_IT_MYSQL_PASSWORD"));
  try(var c=ds.getConnection()){
   assertEquals("MySQL",c.getMetaData().getDatabaseProductName());
   try(var row=c.createStatement().executeQuery("SELECT DATABASE(),COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='ai_memory_packet'")){assertTrue(row.next());assertEquals(url.getPath().substring(1),row.getString(1));assertEquals(1,row.getInt(2));}
   sourceTable(c,"V1.0.0__operation_assistant_mvp.sql","ai_operation_conversation");sourceTable(c,"V1.1.0__customer_service_knowledge_aihub.sql","ai_customer_service_conversation");
   sourceTable(c,"V1.2.3__hr_execution_identity_and_sources.sql","id_hr_session");sourceTable(c,"V1.2.3__hr_execution_identity_and_sources.sql","id_hr_grant");seed(c);
   publishPacketPolicy(c);
  }
  var app=new SpringApplication(ITConfiguration.class);app.setWebApplicationType(WebApplicationType.NONE);
  app.setDefaultProperties(Map.of("spring.config.location","optional:classpath:/memory-it-no-shared-config/","spring.main.banner-mode","off","logging.level.root","WARN","spring.jmx.enabled","false","aiep.memory.packet-enabled",true));
  try(var context=app.run("--spring.config.location=optional:classpath:/memory-it-no-shared-config/")){
   var preferences=context.getBean(MemoryPreferenceService.class);var dependencies=context.getBean(MemoryDependencyService.class);
   var packet=context.getBean(MemoryPacketService.class);var history=context.getBean(MemoryHistoryProjection.class);var memories=context.getBean(MemoryMapper.class);
   var checks=new ArrayList<Executable>();
   for(String kind:List.of("MEMORY_ITEM","SOURCE")){
    String user=kind.equals("MEMORY_ITEM")?"u1":"u2";var scope=scope("t1",user);var actor=context.getBean(IdentityFacade.class).authenticate(TOKENS.get("t1:"+user)).orElseThrow();
    var command=new PreferenceCommand(scope,"response.language","zh-CN",0,"restore-"+kind,null);var saved=preferences.save(actor,command);
    var closure=dependencies.dependencies(scope,"MEMORY_VERSION",saved.id(),saved.versionId());assertEquals(1,closure.size());
    var message=new MemoryHistoryProjection.Message(scope,"history-"+kind,"1","assistant","synthetic");
    dependencies.record(scope,"MESSAGE",message.id(),message.version(),"history-execution-"+kind,closure,List.of(closure),List.of());
    var request=JSON.createObjectNode().put("synthetic",true);String execution="restore-packet-"+kind;
    assertEquals(1,packet.issue(actor,scope,"synthetic-task",execution,request,Instant.now().getEpochSecond()+120,closure).packet().items().size());
    assertEquals(1,history.select(scope,List.of(message)).size());
    byte[] target=MemoryMapper.identity(kind.equals("MEMORY_ITEM")?saved.id():closure.get(0).sourceId());
    // 同名其他tenant清单不能影响本tenant；之后只推进本tenant删除清单，不碰旧item/version/source。
    memories.advanceTombstone(MemoryMapper.identity("t2"),kind,target,1,1,2);assertEquals(saved.versionId(),preferences.get(actor,scope,saved.id()).preference().versionId());
    memories.advanceTombstone(MemoryMapper.identity("t1"),kind,target,1,1,2);
    checks.add(()->assertCode("MEMORY_NOT_FOUND",()->preferences.get(actor,scope,saved.id())));
    checks.add(()->assertTrue(preferences.list(actor,scope,Set.of()).isEmpty(),kind+" list exposed restored body"));
    checks.add(()->assertCode("MEMORY_NOT_FOUND",()->preferences.save(actor,command)));
    checks.add(()->assertCode("MEMORY_NOT_FOUND",()->preferences.save(actor,new PreferenceCommand(scope,"response.language","zh-CN",1,"restore-new-save-"+kind,null))));
    checks.add(()->assertCode("MEMORY_NOT_FOUND",()->preferences.correct(actor,saved.id(),new PreferenceCommand(scope,"response.language","en-US",1,"restore-new-correct-"+kind,null))));
    checks.add(()->assertCode("MEMORY_NOT_FOUND",()->preferences.decide(actor,saved.id(),new PreferenceCommand(scope,"response.language","zh-CN",1,"restore-new-confirm-"+kind,null),"CONFIRM")));
    checks.add(()->assertTrue(history.select(scope,List.of(message)).isEmpty(),kind+" history exposed restored body"));
    checks.add(()->assertCode("MEMORY_SOURCE_CHANGED",()->dependencies.requireCurrent(scope,closure)));
    checks.add(()->assertCode("MEMORY_SOURCE_CHANGED",()->packet.issue(actor,scope,"synthetic-task",execution,request,Instant.now().getEpochSecond()+120,closure)));
    checks.add(()->assertCode("MEMORY_SOURCE_CHANGED",()->packet.issue(actor,scope,"synthetic-task",execution+"-new",request,Instant.now().getEpochSecond()+120,closure)));
   }
   // 只封禁旧历史source时，新当前版本仍可读；历史和旧幂等键不得借用新版本的授权。
   var scope=scope("t2","u1");var actor=context.getBean(IdentityFacade.class).authenticate(TOKENS.get("t2:u1")).orElseThrow();
   var original=new PreferenceCommand(scope,"response.language","zh-CN",0,"restore-history-original",null);var old=preferences.save(actor,original);
   var oldClosure=dependencies.dependencies(scope,"MEMORY_VERSION",old.id(),old.versionId());
   var fresh=preferences.correct(actor,old.id(),new PreferenceCommand(scope,"response.language","en-US",1,"restore-history-fresh",null));
   memories.advanceTombstone(MemoryMapper.identity("t2"),"SOURCE",MemoryMapper.identity(oldClosure.get(0).sourceId()),1,1,2);
   checks.add(()->{var visible=preferences.get(actor,scope,old.id());assertEquals(fresh.versionId(),visible.preference().versionId());assertEquals(1,visible.history().size(),"old source must be checked per historical version");});
   checks.add(()->assertCode("MEMORY_NOT_FOUND",()->preferences.save(actor,original)));
   checks.add(()->explicitReauthorizationStillWorks(context));
   assertAll("restored bodies must obey the already restored deletion manifest",checks);
  }
 }

 static void explicitReauthorizationStillWorks(org.springframework.context.ConfigurableApplicationContext context){
  var scope=scope("t2","u2");var actor=context.getBean(IdentityFacade.class).authenticate(TOKENS.get("t2:u2")).orElseThrow();
  var preferences=context.getBean(MemoryPreferenceService.class);var memories=context.getBean(MemoryMapper.class);var dependencies=context.getBean(MemoryDependencyService.class);
  var saved=preferences.save(actor,new PreferenceCommand(scope,"response.language","zh-CN",0,"restore-reauth-original",null));
  var original=memories.findItemForUpdate(MemoryMapper.identity("t2"),MemoryMapper.identity(saved.id()));
  var forgotten=context.getBean(MemoryForgetService.class).forget(actor,new MemoryForgetService.ForgetCommand(scope,saved.id(),1,"restore-reauth-forget","FORGET_AND_SUPPRESS"));
  context.getBean(MemoryForgetIntegrationTest.TestCleanupAck.class).allConfirmed=true;
  context.getBean(MemoryDeletionService.class).compensate("t2",forgotten.jobId());
  var deleted=memories.findItemForUpdate(MemoryMapper.identity("t2"),MemoryMapper.identity(saved.id()));assertEquals("DELETED",deleted.lifecycle());
  var fresh=context.getBean(MemorySuppressionService.class).reauthorize(actor,forgotten.suppressionId(),new MemorySuppressionService.ReauthorizationCommand(scope,saved.id(),"response.language","en-US",deleted.revision(),forgotten.suppressionRevision(),"restore-reauth-new","ALLOW_REMEMBER"));
  var current=memories.findItemForUpdate(MemoryMapper.identity("t2"),MemoryMapper.identity(saved.id()));
  assertArrayEquals(original.id(),current.id());assertTrue(current.grantEpoch()>deleted.grantEpoch());assertNotEquals(saved.versionId(),fresh.versionId());
  assertEquals(fresh.versionId(),preferences.get(actor,scope,saved.id()).preference().versionId());assertEquals(1,preferences.list(actor,scope,Set.of()).size());
  assertEquals(1,preferences.get(actor,scope,saved.id()).history().size());
  dependencies.requireCurrent(scope,dependencies.dependencies(scope,"MEMORY_VERSION",fresh.id(),fresh.versionId()));
 }
 static MemoryScopeDTO scope(String tenant,String user){return new MemoryScopeDTO(tenant,user,"operations","operations","CONVERSATION",SESSIONS.get(tenant+":"+user+":operations:1"));}
 static void assertCode(String code,Executable operation){assertEquals(code,assertThrows(MemoryException.class,operation).code());}
 static void publishPacketPolicy(Connection c)throws Exception{
  try(var q=c.prepareStatement("SELECT policy_json FROM ai_memory_policy_version WHERE tenant_id=? AND policy_id=? AND version_id=?");var insert=c.prepareStatement("INSERT INTO ai_memory_policy_version(tenant_id,policy_id,version_id,policy_json,content_hmac) VALUES(?,?,?,?,?)");var publish=c.prepareStatement("UPDATE ai_memory_policy SET current_version_id=? WHERE tenant_id=? AND id=?")){
   for(String tenant:List.of("t1","t2")){
    q.setBytes(1,MemoryMapper.identity(tenant));q.setBytes(2,MemoryMapper.identity("policy-operations"));q.setBytes(3,MemoryMapper.identity("v1"));String json;
    try(var row=q.executeQuery()){assertTrue(row.next());var root=(com.fasterxml.jackson.databind.node.ObjectNode)JSON.readTree(row.getString(1));root.set("context",JSON.valueToTree(Map.of("enabled",true,"packetTtlSeconds",60,"sourceTypes",List.of("USER_PREFERENCE_DECISION"),"executionGrants",List.of(Map.of("node_id","direct","execution_agent_id","operations","purpose","assistant_response")))));json=root.toString();}
    insert.setBytes(1,MemoryMapper.identity(tenant));insert.setBytes(2,MemoryMapper.identity("policy-operations"));insert.setBytes(3,MemoryMapper.identity("restore-policy"));insert.setString(4,json);insert.setBytes(5,random(32));assertEquals(1,insert.executeUpdate());
    publish.setBytes(1,MemoryMapper.identity("restore-policy"));publish.setBytes(2,MemoryMapper.identity(tenant));publish.setBytes(3,MemoryMapper.identity("policy-operations"));assertEquals(1,publish.executeUpdate());
   }
  }
 }
}

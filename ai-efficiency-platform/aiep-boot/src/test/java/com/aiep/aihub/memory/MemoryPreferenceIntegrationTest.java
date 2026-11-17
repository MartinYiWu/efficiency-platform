package com.aiep.aihub.memory;

import com.aiep.aihub.api.memory.MemoryFacade;
import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.facade.memory.DefaultMemoryFacade;
import com.aiep.aihub.repository.memory.MemoryMapper;
import com.aiep.aihub.web.memory.*;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.identity.facade.DatabaseIdentityFacade;
import com.aiep.identity.repository.IdentitySessionMapper;
import com.aiep.platformcore.config.TraceIdFilter;
import com.baomidou.mybatisplus.extension.spring.MybatisSqlSessionFactoryBean;
import com.baomidou.mybatisplus.autoconfigure.MybatisPlusAutoConfiguration;
import com.fasterxml.jackson.databind.*;
import java.net.URI;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.sql.*;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import javax.sql.DataSource;
import org.apache.ibatis.session.SqlSessionFactory;
import org.apache.ibatis.executor.Executor;
import org.apache.ibatis.mapping.MappedStatement;
import org.apache.ibatis.plugin.*;
import org.apache.ibatis.session.RowBounds;
import org.apache.ibatis.session.ResultHandler;
import java.util.concurrent.atomic.AtomicInteger;
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
import static org.junit.jupiter.api.Assertions.*;

/** 仅root受控随机schema：生产MVC/认证数据库/真实Mapper/本地事务；无共享配置、模型或mock服务。 */
@EnabledIfSystemProperty(named="memory.integration.enabled",matches="true")
class MemoryPreferenceIntegrationTest {
 static final ObjectMapper JSON=new ObjectMapper().findAndRegisterModules();
 static final HttpClient CLIENT=HttpClient.newHttpClient();
 static String base;
 static final CreationGate GATE=new CreationGate();
 static final Map<String,String> TOKENS=new HashMap<>(),SESSIONS=new HashMap<>();
 @Configuration(proxyBeanMethods=false)
 @EnableAutoConfiguration(exclude={DataSourceAutoConfiguration.class,MybatisPlusAutoConfiguration.class},excludeName={"org.redisson.spring.starter.RedissonAutoConfigurationV2","org.springframework.boot.autoconfigure.data.redis.RedisAutoConfiguration","org.springframework.boot.autoconfigure.data.redis.RedisRepositoriesAutoConfiguration"})
 @EnableTransactionManagement
 @Import({ConversationScopeResolver.class,MemoryScopePolicy.class,MemorySessionBindingService.class,MemoryPolicyService.class,MemoryVersionService.class,MemoryPreferenceService.class,DefaultMemoryFacade.class,MemoryActorResolver.class,MemoryController.class,MemoryExceptionHandler.class,TraceIdFilter.class})
 static class ITConfiguration {
  @Bean DataSource dataSource(){return new DriverManagerDataSource(required("MEMORY_IT_MYSQL_JDBC_URL"),required("MEMORY_IT_MYSQL_USER"),required("MEMORY_IT_MYSQL_PASSWORD"));}
  @Bean PlatformTransactionManager transactionManager(DataSource ds){return new DataSourceTransactionManager(ds);}
  @Bean SqlSessionFactory sqlSessionFactory(DataSource ds)throws Exception{var factory=new MybatisSqlSessionFactoryBean();factory.setDataSource(ds);factory.setMapperLocations(new ClassPathResource("mapper/memory/MemoryMapper.xml"),new ClassPathResource("mapper/identity/IdentitySessionMapper.xml"));var conf=new com.baomidou.mybatisplus.core.MybatisConfiguration();conf.setMapUnderscoreToCamelCase(true);factory.setConfiguration(conf);factory.setPlugins(GATE);return factory.getObject();}
  @Bean MemoryMapper memoryMapper(SqlSessionFactory factory){return new SqlSessionTemplate(factory).getMapper(MemoryMapper.class);}
  @Bean IdentitySessionMapper identityMapper(SqlSessionFactory factory){return new SqlSessionTemplate(factory).getMapper(IdentitySessionMapper.class);}
  @Bean IdentityFacade identity(IdentitySessionMapper mapper){return new DatabaseIdentityFacade(mapper);}
  @Bean MemoryValueCodec codec(){byte[] key=random(32),mac=random(32);return new MemoryValueCodec("it","{\"it\":\""+Base64.getEncoder().encodeToString(key)+"\"}",Base64.getEncoder().encodeToString(mac));}
 }
 @Test void productionHttpOwnershipEncryptedVersionsAndRealFirstWriteCompetition()throws Exception {
  var ds=checkedDataSource();
  try(var connection=ds.getConnection()){
   sourceTable(connection,"V1.0.0__operation_assistant_mvp.sql","ai_operation_conversation");sourceTable(connection,"V1.1.0__customer_service_knowledge_aihub.sql","ai_customer_service_conversation");sourceTable(connection,"V1.2.3__hr_execution_identity_and_sources.sql","id_hr_session");sourceTable(connection,"V1.2.3__hr_execution_identity_and_sources.sql","id_hr_grant");seed(connection);
  }
  var app=new SpringApplication(ITConfiguration.class);app.setDefaultProperties(Map.of("spring.config.location","optional:classpath:/memory-it-no-shared-config/","server.address","127.0.0.1","server.port","0","spring.main.banner-mode","off","logging.level.root","WARN","spring.jmx.enabled","false"));
  try(var context=(ServletWebServerApplicationContext)app.run("--spring.config.location=optional:classpath:/memory-it-no-shared-config/","--server.address=127.0.0.1","--server.port=0")){
   base="http://127.0.0.1:"+context.getWebServer().getPort()+"/api/aihub/memories";
   try(var c=ds.getConnection()){
    String legacy;
    try(var p=c.prepareStatement("SELECT policy_json FROM ai_memory_policy_version WHERE tenant_id=_binary't1' AND policy_id=_binary'policy-operations' AND version_id=_binary'v1'");var r=p.executeQuery()){
     assertTrue(r.next());var root=(com.fasterxml.jackson.databind.node.ObjectNode)JSON.readTree(r.getString(1));root.remove("artifacts");legacy=root.toString();
    }
    try(var p=c.prepareStatement("INSERT INTO ai_memory_policy_version(tenant_id,policy_id,version_id,policy_json,content_hmac) VALUES(_binary't1',_binary'policy-operations',_binary'legacy-no-artifacts',?,?)")){p.setString(1,legacy);p.setBytes(2,random(32));assertEquals(1,p.executeUpdate());}
    try(var p=c.prepareStatement("UPDATE ai_memory_policy SET current_version_id=_binary'legacy-no-artifacts' WHERE tenant_id=_binary't1' AND id=_binary'policy-operations'")){assertEquals(1,p.executeUpdate());}
    String legacyCommand=JSON.writeValueAsString(Map.of("topAgent","operations","fieldKey","response.language","value","zh-CN","expectedRevision",0,"idempotencyKey","legacy-reject"));
    assertEquals("FEATURE_DISABLED",post("",TOKENS.get("t1:u1"),legacyCommand,422).path("code").asText());
    try(var r=c.createStatement().executeQuery("SELECT (SELECT COUNT(*) FROM ai_memory_item),(SELECT COUNT(*) FROM ai_memory_version),(SELECT COUNT(*) FROM ai_memory_decision)")){assertTrue(r.next());assertEquals(0,r.getInt(1));assertEquals(0,r.getInt(2));assertEquals(0,r.getInt(3));}
    try(var p=c.prepareStatement("UPDATE ai_memory_policy SET current_version_id=_binary'v1' WHERE tenant_id=_binary't1' AND id=_binary'policy-operations'")){assertEquals(1,p.executeUpdate());}
   }
   var scopes=new ArrayList<String>();for(String tenant:List.of("t1","t2"))for(String user:List.of("u1","u2"))for(String agent:List.of("operations","customer-service"))scopes.add(tenant+":"+user+":"+agent);
   get("?topAgent=operations",TOKENS.get("t1:u1"),200);
   try(var c=ds.getConnection();var r=c.createStatement().executeQuery("SELECT COUNT(*) FROM ai_memory_session_binding")){assertTrue(r.next());assertEquals(0,r.getInt(1));}
   Map<String,String> ids=new HashMap<>();
   for(String scope:scopes){var parts=scope.split(":");String session=SESSIONS.get(scope+":1");
    String payload=command(parts[2],session,"response.language","zh-CN",0,"save-"+scope);
    if(scope.equals("t1:u1:operations")){var manual=(com.fasterxml.jackson.databind.node.ObjectNode)JSON.readTree(payload);manual.remove("sessionId");payload=manual.toString();}
    var saved=post("",token(parts),payload,200);String id=saved.path("data").path("id").asText();ids.put(scope,id);
    assertEquals("ACTIVE",saved.path("data").path("status").asText());assertFalse(saved.toString().contains("tenantId"));assertFalse(saved.toString().contains("sessionRef"));
    var otherSession=get("?topAgent="+parts[2]+"&sessionId="+SESSIONS.get(scope+":2"),token(parts),200);
    assertEquals(1,otherSession.path("data").path("total").asInt());assertEquals(id,otherSession.path("data").path("items").get(0).path("id").asText());
   }
   String key="t1:u1:operations",id=ids.get(key),credential=TOKENS.get("t1:u1"),session=SESSIONS.get(key+":1"),query="?topAgent=operations&sessionId="+session;
   try(var c=ds.getConnection();var p=c.prepareStatement("SELECT id,current_version_id FROM ai_memory_item WHERE tenant_id=_binary't1' AND id=?")){
    p.setBytes(1,MemoryMapper.identity(id));try(var r=p.executeQuery()){
     assertTrue(r.next());var versions=List.of(new MemoryMapper.VersionIdentityPO(r.getBytes(1),r.getBytes(2)));
     var rows=context.getBean(MemoryMapper.class).listVersionPolicies(MemoryMapper.identity("t1"),versions);
     assertEquals(1,rows.size());assertArrayEquals(versions.get(0).itemId(),rows.get(0).itemId());assertArrayEquals(versions.get(0).versionId(),rows.get(0).versionId());
     context.getBean(MemoryPolicyService.class).requireVersionArtifacts(MemoryMapper.identity("t1"),versions);
     assertTrue(context.getBean(MemoryMapper.class).listVersionPolicies(MemoryMapper.identity("t2"),versions).isEmpty());
     assertTrue(context.getBean(MemoryMapper.class).listVersionPolicies(MemoryMapper.identity("t1"),List.of()).isEmpty());
    }
   }
   var before=get("/"+id+query,credential,200);String expiry=before.path("data").path("preference").path("expiresAt").asText();
   var corrected=post("/"+id+"/corrections",credential,command("operations",session,"response.language","en-US",1,"correction"),200);
   assertEquals(2,corrected.path("data").path("revision").asLong());
   var detail=get("/"+id+query,credential,200);assertEquals("en-US",detail.path("data").path("preference").path("value").asText());assertEquals(2,detail.path("data").path("history").size());assertEquals("SUPERSEDED",detail.path("data").path("history").get(1).path("status").asText());
   assertEquals(expiry,detail.path("data").path("history").get(1).path("expiresAt").asText());
   String reject=command("operations",session,"response.language","en-US",2,"reject").replace("}",",\"action\":\"REJECT\"}");post("/"+id+"/decisions",credential,reject,200);
   var stable=get("/"+id+query,credential,200);assertEquals(corrected.path("data").path("versionId"),stable.path("data").path("preference").path("versionId"));
   post("/"+id+"/corrections",credential,command("operations",session,"response.language","zh-CN",1,"stale"),409);
   post("",credential,command("operations",session,"response.language","en-US",0,"save-"+key),409);
   get("/"+id+"?topAgent=operations&sessionId="+SESSIONS.get("t1:u2:operations:1"),TOKENS.get("t1:u2"),404);
   get("/"+id+"?topAgent=operations&sessionId="+SESSIONS.get("t2:u1:operations:1"),TOKENS.get("t2:u1"),404);
   get("/"+id+"?topAgent=customer-service&sessionId="+SESSIONS.get("t1:u1:customer-service:1"),credential,404);
   get("/"+id+"?topAgent=operations&sessionId="+SESSIONS.get("t1:u2:operations:1"),credential,403);
   // 竞争前绑定两个独立业务会话，竞争只测记忆逻辑unique，不混入D11首次binding间隙死锁。
   race(credential,session,SESSIONS.get(key+":2"),"response.detail_level","concise","concise",true);
   race(credential,session,SESSIONS.get(key+":2"),"response.format","prose","bullets",false);
   try(var connection=ds.getConnection()){
    try(var rows=connection.createStatement().executeQuery("SELECT COUNT(*) FROM ai_memory_version v JOIN ai_memory_item i ON i.tenant_id=v.tenant_id AND i.id=v.item_id WHERE v.status='ACTIVE' AND i.current_version_id=v.id")){assertTrue(rows.next());assertEquals(10,rows.getInt(1));}
    try(var ps=connection.prepareStatement("SELECT i.revision,COUNT(v.id),SUM(v.status='ACTIVE') FROM ai_memory_item i JOIN ai_memory_version v ON v.tenant_id=i.tenant_id AND v.item_id=i.id WHERE i.tenant_id=? AND i.id=? GROUP BY i.revision")){ps.setBytes(1,MemoryMapper.identity("t1"));ps.setBytes(2,MemoryMapper.identity(id));try(var r=ps.executeQuery()){assertTrue(r.next());assertEquals(2,r.getLong(1));assertEquals(2,r.getLong(2));assertEquals(1,r.getLong(3));}}
    try(var r=connection.createStatement().executeQuery("SELECT COUNT(*) FROM ai_memory_version WHERE encrypted_payload IN (_binary'zh-CN',_binary'en-US')")){assertTrue(r.next());assertEquals(0,r.getInt(1));}
    try(var ps=connection.prepareStatement("UPDATE ai_memory_item SET lifecycle='REVOKED' WHERE tenant_id=? AND id=?")){ps.setBytes(1,MemoryMapper.identity("t1"));ps.setBytes(2,MemoryMapper.identity(id));assertEquals(1,ps.executeUpdate());}
    get("/"+id+query,credential,404);
    try(var ps=connection.prepareStatement("UPDATE id_hr_session SET revoked_at=UTC_TIMESTAMP(6) WHERE credential_hash=?")){ps.setString(1,hash(credential));assertEquals(1,ps.executeUpdate());}
    get(query,credential,401);
   }
  }
 }
 static void race(String token,String first,String second,String field,String a,String b,boolean same)throws Exception{
  GATE.field=field;GATE.missing.set(0);GATE.connections.clear();GATE.barrier=new CyclicBarrier(2);
  var barrier=new CyclicBarrier(2);var pool=Executors.newFixedThreadPool(2);try{
   var one=pool.submit(()->{barrier.await(10,TimeUnit.SECONDS);return rawPost("",token,command("operations",first,field,a,0,"race-a-"+field));});
   var two=pool.submit(()->{barrier.await(10,TimeUnit.SECONDS);return rawPost("",token,command("operations",second,field,b,0,"race-b-"+field));});
   var left=one.get(30,TimeUnit.SECONDS);var right=two.get(30,TimeUnit.SECONDS);
   assertEquals(2,GATE.missing.get());assertEquals(2,GATE.connections.size());
   if(same){assertEquals(200,left.statusCode());assertEquals(200,right.statusCode());assertEquals(JSON.readTree(left.body()).path("data").path("id"),JSON.readTree(right.body()).path("data").path("id"));}
   else assertEquals(Set.of(200,409),Set.of(left.statusCode(),right.statusCode()));
   System.out.println("D12 real preference race: same="+same+", connections="+GATE.connections.size()+", missingReads="+GATE.missing.get());
  }finally{GATE.field=null;pool.shutdownNow();}
 }
 @Intercepts(@Signature(type=Executor.class,method="query",args={MappedStatement.class,Object.class,RowBounds.class,ResultHandler.class}))
 static class CreationGate implements Interceptor {
  volatile String field;volatile CyclicBarrier barrier;final AtomicInteger missing=new AtomicInteger();final Set<Long> connections=ConcurrentHashMap.newKeySet();
  public Object intercept(Invocation invocation)throws Throwable {
   Object result=invocation.proceed();var statement=(MappedStatement)invocation.getArgs()[0];
   if(field!=null&&statement.getId().endsWith(".findPreferenceItem")&&invocation.getArgs()[1] instanceof Map<?,?> parameters&&field.equals(parameters.get("field"))&&result instanceof List<?> rows&&rows.isEmpty()) {
    if(missing.incrementAndGet()<=2){var executor=(Executor)invocation.getTarget();try(var query=executor.getTransaction().getConnection().createStatement();var ids=query.executeQuery("SELECT CONNECTION_ID()")){assertTrue(ids.next());connections.add(ids.getLong(1));}barrier.await(15,TimeUnit.SECONDS);}
   }
   return result;
  }
 }
 static DriverManagerDataSource checkedDataSource()throws Exception{
  String url=required("MEMORY_IT_MYSQL_JDBC_URL");assertTrue(url.startsWith("jdbc:mysql://"));var uri=URI.create(url.substring(5));assertNull(uri.getUserInfo());assertTrue(Set.of("127.0.0.1","localhost","::1","[::1]").contains(uri.getHost()));String schema=uri.getPath().substring(1);assertTrue(schema.matches("aiep_memory_it_[0-9]{8}_[0-9a-f]{10}"));var ds=new DriverManagerDataSource(url,required("MEMORY_IT_MYSQL_USER"),required("MEMORY_IT_MYSQL_PASSWORD"));
  try(var c=ds.getConnection();var r=c.createStatement().executeQuery("SELECT DATABASE(),(SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name LIKE 'ai\\_memory\\_%')")){assertEquals("MySQL",c.getMetaData().getDatabaseProductName());assertTrue(r.next());assertEquals(schema,r.getString(1));assertEquals(12,r.getInt(2));}return ds;
 }
 static void sourceTable(Connection c,String migration,String table)throws Exception{String sql=Files.readString(Path.of("../sql/migration",migration));String start="CREATE TABLE "+table+" (";int from=sql.indexOf(start);assertTrue(from>=0);int end=sql.indexOf(';',from);try(var s=c.createStatement()){s.execute(sql.substring(from,end+1));}}
 static void seed(Connection c)throws Exception{
  for(String tenant:List.of("t1","t2")){
   for(String user:List.of("u1","u2")){
    String token=Base64.getUrlEncoder().withoutPadding().encodeToString(random(48));TOKENS.put(tenant+":"+user,token);
    try(var ps=c.prepareStatement("INSERT INTO id_hr_session(credential_hash,tenant_id,user_id,expires_at) VALUES(?,?,?,?)")){ps.setString(1,hash(token));ps.setString(2,tenant);ps.setString(3,user);ps.setTimestamp(4,Timestamp.from(Instant.now().plusSeconds(3600)));ps.executeUpdate();}
    for(String agent:List.of("operations","customer-service"))for(int n=1;n<=2;n++){
     String session=UUID.randomUUID().toString();SESSIONS.put(tenant+":"+user+":"+agent+":"+n,session);String table=agent.equals("operations")?"ai_operation_conversation":"ai_customer_service_conversation";
     try(var ps=c.prepareStatement("INSERT INTO "+table+"(id,tenant_id,user_id,title,status,created_at,updated_at) VALUES(?,?,?,'synthetic','ACTIVE',UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))")){ps.setString(1,session);ps.setString(2,tenant);ps.setString(3,user);ps.executeUpdate();}
    }
   }
   for(String agent:List.of("operations","customer-service","hr")){
    String policy="policy-"+agent,version="v1";String json="{\"fields\":{\"response.language\":{\"enabled\":true,\"values\":[\"zh-CN\",\"en-US\"],\"retentionSeconds\":3600,\"sourceRetentionSeconds\":1200},\"response.detail_level\":{\"enabled\":true,\"values\":[\"concise\",\"standard\",\"detailed\"],\"retentionSeconds\":3600,\"sourceRetentionSeconds\":1200},\"response.format\":{\"enabled\":true,\"values\":[\"prose\",\"bullets\",\"table\"],\"retentionSeconds\":3600,\"sourceRetentionSeconds\":1200}}}";
    var published=(com.fasterxml.jackson.databind.node.ObjectNode)JSON.readTree(json);
    published.set("artifacts",JSON.valueToTree(Map.of("schema_version","memory-artifacts/1","index_mode","NOT_PROVISIONED","index_backends",List.of())));
    json=JSON.writeValueAsString(published);
    try(var ps=c.prepareStatement("INSERT INTO ai_memory_policy(tenant_id,id,domain) VALUES(?,?,?)")){ps.setBytes(1,MemoryMapper.identity(tenant));ps.setBytes(2,MemoryMapper.identity(policy));ps.setBytes(3,MemoryMapper.identity(agent));ps.executeUpdate();}
    try(var ps=c.prepareStatement("INSERT INTO ai_memory_policy_version(tenant_id,policy_id,version_id,policy_json,content_hmac) VALUES(?,?,?,?,?)")){ps.setBytes(1,MemoryMapper.identity(tenant));ps.setBytes(2,MemoryMapper.identity(policy));ps.setBytes(3,MemoryMapper.identity(version));ps.setString(4,json);ps.setBytes(5,random(32));ps.executeUpdate();}
    try(var ps=c.prepareStatement("UPDATE ai_memory_policy SET enabled=TRUE,current_version_id=? WHERE tenant_id=? AND id=?")){ps.setBytes(1,MemoryMapper.identity(version));ps.setBytes(2,MemoryMapper.identity(tenant));ps.setBytes(3,MemoryMapper.identity(policy));ps.executeUpdate();}
   }
  }
 }
 static String token(String[] parts){return TOKENS.get(parts[0]+":"+parts[1]);}
 static String command(String agent,String session,String field,String value,long revision,String key)throws Exception{return JSON.writeValueAsString(Map.of("topAgent",agent,"sessionId",session,"fieldKey",field,"value",value,"expectedRevision",revision,"idempotencyKey",key));}
 static HttpResponse<String> rawPost(String path,String token,String body)throws Exception{return CLIENT.send(HttpRequest.newBuilder(URI.create(base+path)).header("Authorization","Bearer "+token).header("Content-Type","application/json").POST(HttpRequest.BodyPublishers.ofString(body)).build(),HttpResponse.BodyHandlers.ofString());}
 static JsonNode post(String path,String token,String body,int expected)throws Exception{var response=rawPost(path,token,body);assertEquals(expected,response.statusCode());return checked(response);}
 static JsonNode get(String path,String token,int expected)throws Exception{var response=CLIENT.send(HttpRequest.newBuilder(URI.create(base+path)).header("Authorization","Bearer "+token).GET().build(),HttpResponse.BodyHandlers.ofString());assertEquals(expected,response.statusCode());return checked(response);}
 static JsonNode checked(HttpResponse<String> response)throws Exception{var json=JSON.readTree(response.body());assertEquals(response.headers().firstValue("X-Trace-Id").orElseThrow(),json.path("traceId").asText());if(response.statusCode()>=400)assertTrue(json.path("data").isNull());return json;}
 static String hash(String token)throws Exception{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(token.getBytes(StandardCharsets.UTF_8)));}
 static byte[] random(int size){byte[] result=new byte[size];new SecureRandom().nextBytes(result);return result;}
 static String required(String name){String value=System.getenv(name);if(value==null||value.isBlank())throw new AssertionError("显式隔离环境变量缺失");return value;}
}

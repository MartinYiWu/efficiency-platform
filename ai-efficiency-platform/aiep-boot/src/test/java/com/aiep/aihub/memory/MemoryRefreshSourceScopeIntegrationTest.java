package com.aiep.aihub.memory;

import com.aiep.aihub.api.memory.*;
import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.repository.memory.*;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.identity.facade.DatabaseIdentityFacade;
import com.aiep.identity.repository.IdentitySessionMapper;
import com.aiep.platformai.api.dto.*;
import com.baomidou.mybatisplus.extension.spring.MybatisSqlSessionFactoryBean;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.time.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.*;
import static com.aiep.aihub.memory.MemoryPreferenceIntegrationTest.*;
import static org.junit.jupiter.api.Assertions.*;

/** I1只使用root随机schema，真实业务消息/Mapper/身份，不以相同正文代替原会话归属。 */
@EnabledIfSystemProperty(named="memory.integration.enabled",matches="true")
class MemoryRefreshSourceScopeIntegrationTest {
    static final ObjectMapper JSON=new ObjectMapper();
    static byte[] b(String text){return MemoryMapper.identity(text);}

    @Test void originalMessageConversationMustRemainExactInBothDomains()throws Exception {
        String url=required("MEMORY_IT_MYSQL_JDBC_URL");var uri=URI.create(url.substring(5));
        assertEquals("127.0.0.1",uri.getHost());assertTrue(uri.getPath().matches("/aiep_memory_it_[0-9]{8}_[0-9a-f]{10}"));
        var ds=new DriverManagerDataSource(url,required("MEMORY_IT_MYSQL_USER"),required("MEMORY_IT_MYSQL_PASSWORD"));
        try(var c=ds.getConnection()) {
            for(String table:List.of("ai_operation_conversation","ai_operation_message"))sourceTable(c,"V1.0.0__operation_assistant_mvp.sql",table);
            for(String table:List.of("ai_customer_service_conversation","ai_customer_service_message"))sourceTable(c,"V1.1.0__customer_service_knowledge_aihub.sql",table);
            for(String table:List.of("id_hr_session","id_hr_grant"))sourceTable(c,"V1.2.3__hr_execution_identity_and_sources.sql",table);
            seed(c);
            for(String domain:List.of("operations","customer-service")) {
                String raw;
                try(var q=c.prepareStatement("SELECT policy_json FROM ai_memory_policy_version WHERE tenant_id='t1' AND policy_id=? AND version_id='v1'")) {
                    q.setBytes(1,b("policy-"+domain));try(var r=q.executeQuery()){assertTrue(r.next());raw=r.getString(1);}
                }
                var policy=(com.fasterxml.jackson.databind.node.ObjectNode)JSON.readTree(raw);
                policy.set("context",JSON.valueToTree(Map.of("enabled",true,"packetTtlSeconds",60,
                    "sourceTypes",List.of("USER_PREFERENCE_DECISION","CURRENT_USER_MESSAGE"),
                    "executionGrants",List.of(Map.of("node_id","direct","execution_agent_id",domain,"purpose","assistant_response")))));
                try(var q=c.prepareStatement("INSERT INTO ai_memory_policy_version(tenant_id,policy_id,version_id,policy_json,content_hmac) VALUES('t1',?,'refresh-scope-it',?,?)")) {
                    q.setBytes(1,b("policy-"+domain));q.setString(2,policy.toString());q.setBytes(3,random(32));assertEquals(1,q.executeUpdate());
                }
                try(var q=c.prepareStatement("UPDATE ai_memory_policy SET current_version_id='refresh-scope-it' WHERE tenant_id='t1' AND id=?")) {
                    q.setBytes(1,b("policy-"+domain));assertEquals(1,q.executeUpdate());
                }
            }
        }
        var factory=new MybatisSqlSessionFactoryBean();factory.setDataSource(ds);
        factory.setMapperLocations(new ClassPathResource("mapper/memory/MemoryMapper.xml"),new ClassPathResource("mapper/memory/MemoryPacketMapper.xml"),new ClassPathResource("mapper/memory/MemoryRefreshMapper.xml"),new ClassPathResource("mapper/identity/IdentitySessionMapper.xml"));
        var conf=new com.baomidou.mybatisplus.core.MybatisConfiguration();conf.setMapUnderscoreToCamelCase(true);factory.setConfiguration(conf);
        var sql=new SqlSessionTemplate(factory.getObject());var memory=sql.getMapper(MemoryMapper.class);var packets=sql.getMapper(MemoryPacketMapper.class);var refresh=sql.getMapper(MemoryRefreshMapper.class);
        IdentityFacade identity=new DatabaseIdentityFacade(sql.getMapper(IdentitySessionMapper.class));
        var actor=identity.authenticate(TOKENS.get("t1:u1")).orElseThrow();
        var scopes=new MemoryScopePolicy(identity,null);var bindings=new MemorySessionBindingService(memory,scopes,new ConversationScopeResolver());
        var tx=new DataSourceTransactionManager(ds);var policies=new MemoryPolicyService(memory);
        var codec=new MemoryValueCodec("it","{\"it\":\""+Base64.getEncoder().encodeToString(random(32))+"\"}",Base64.getEncoder().encodeToString(random(32)));
        var preferences=new MemoryPreferenceService(memory,scopes,bindings,policies,new MemoryVersionService(memory,codec),codec,tx);
        var seconds=new AtomicLong(Instant.now().getEpochSecond());
        var clock=new Clock(){public ZoneId getZone(){return ZoneOffset.UTC;}public Clock withZone(ZoneId zone){return this;}public Instant instant(){return Instant.ofEpochSecond(seconds.get());}};
        var service=new MemoryPacketService(true,memory,packets,scopes,bindings,policies,preferences,new MemoryDependencyService(packets,clock),codec,tx,clock,true,refresh,identity);
        assertAll("双业务必须拒绝同用户同正文跨会话",
            ()->verifyDomain(ds,packets,refresh,service,actor,clock,seconds,"operations"),
            ()->verifyDomain(ds,packets,refresh,service,actor,clock,seconds,"customer-service"));
        System.out.println("D16RF05R realMySQL=passed domains=operations,customer-service unchanged=accepted sameUserOtherConversation=denied crossUser=denied crossTenant=denied deleted=denied bodyChanged=denied sourceTuple=unchanged candidateCount=unchanged paidCalls=0");
    }

    private static void verifyDomain(DriverManagerDataSource ds,MemoryPacketMapper packets,MemoryRefreshMapper refresh,
            MemoryPacketService service,IdentityFacade.Subject actor,Clock clock,AtomicLong seconds,String domain)throws Exception {
        String table=domain.equals("operations")?"ai_operation_message":"ai_customer_service_message";
        String column=domain.equals("operations")?"content":"content_markdown";
        String session=SESSIONS.get("t1:u1:"+domain+":1"),message=UUID.randomUUID().toString(),execution="scope-"+domain;
        var scope=new MemoryScopeDTO("t1","u1",domain,domain,"CONVERSATION",session);
        insertMessage(ds,table,column,message,session);
        String sourceId="source-"+domain,digest=hash("synthetic-scope-input");
        assertEquals(1,packets.insertInputSource(b("t1"),b(sourceId),b(message),b(digest),clock.instant().plusSeconds(900)));
        var source=packets.findSource(b("t1"),b(sourceId));assertNotNull(source);
        var direct=new MemoryContextPacket.Dependency(source.sourceType(),sourceId,digest,source.grantEpoch(),source.sourceEpoch(),source.deletionEpoch());
        var original=service.issue(actor,scope,execution,execution,JSON.readTree("{\"message\":\"synthetic-scope-input\"}"),seconds.get()+300,List.of(direct));
        seconds.addAndGet(61);var wait=MemoryRefreshIntegrationTest.wait(original,1,"wait-"+domain,"a".repeat(64),0);
        String key="resume-"+domain;var request=service.prepareRefresh(scope,wait,key);
        assertNotNull(refresh.findCandidate(b("t1"),b(execution),b(key)));
        assertAll(domain,
            ()->assertMovedMessageDenied(ds,table,message,session,SESSIONS.get("t1:u1:"+domain+":2"),service,scope,wait,key,"same-user-other-conversation"),
            ()->assertMovedMessageDenied(ds,table,message,session,SESSIONS.get("t1:u2:"+domain+":1"),service,scope,wait,key,"other-user"),
            ()->assertMovedMessageDenied(ds,table,message,session,SESSIONS.get("t2:u1:"+domain+":1"),service,scope,wait,key,"other-tenant"),
            ()->{
                try(var c=ds.getConnection();var q=c.prepareStatement("UPDATE "+table+" SET "+column+"='changed-scope-input' WHERE id=?")){q.setString(1,message);assertEquals(1,q.executeUpdate());}
                try {assertEquals("MEMORY_SOURCE_CHANGED",assertThrows(MemoryContracts.MemoryException.class,()->service.prepareRefresh(scope,wait,key),domain+" changed-body").code());}
                finally {try(var c=ds.getConnection();var q=c.prepareStatement("UPDATE "+table+" SET "+column+"='synthetic-scope-input' WHERE id=?")){q.setString(1,message);assertEquals(1,q.executeUpdate());}}
            },
            ()->{
                try(var c=ds.getConnection();var q=c.prepareStatement("DELETE FROM "+table+" WHERE id=?")){q.setString(1,message);assertEquals(1,q.executeUpdate());}
                try {assertEquals("MEMORY_SOURCE_CHANGED",assertThrows(MemoryContracts.MemoryException.class,()->service.prepareRefresh(scope,wait,key),domain+" deleted-message").code());}
                finally {insertMessage(ds,table,column,message,session);}
            });
        assertEquals(request,service.prepareRefresh(scope,wait,key));
        var after=packets.findSource(b("t1"),b(sourceId));assertArrayEquals(source.sourceVersion(),after.sourceVersion());
        assertEquals(source.grantEpoch(),after.grantEpoch());assertEquals(source.sourceEpoch(),after.sourceEpoch());assertEquals(source.deletionEpoch(),after.deletionEpoch());
        assertEquals(2,refresh.highestRevision(b("t1"),b(execution)));assertEquals("PREPARED",refresh.findCandidate(b("t1"),b(execution),b(key)).phase());
    }

    private static void assertMovedMessageDenied(DriverManagerDataSource ds,String table,String message,String original,String destination,
            MemoryPacketService service,MemoryScopeDTO scope,MemoryContextWait wait,String key,String scenario)throws Exception {
        try(var c=ds.getConnection();var q=c.prepareStatement("UPDATE "+table+" SET conversation_id=? WHERE id=?")){q.setString(1,destination);q.setString(2,message);assertEquals(1,q.executeUpdate());}
        try {assertEquals("MEMORY_SOURCE_CHANGED",assertThrows(MemoryContracts.MemoryException.class,()->service.prepareRefresh(scope,wait,key),scope.domain()+" "+scenario).code());}
        finally {try(var c=ds.getConnection();var q=c.prepareStatement("UPDATE "+table+" SET conversation_id=? WHERE id=?")){q.setString(1,original);q.setString(2,message);assertEquals(1,q.executeUpdate());}}
    }
    private static void insertMessage(DriverManagerDataSource ds,String table,String column,String message,String session)throws Exception {
        try(var c=ds.getConnection();var q=c.prepareStatement("INSERT INTO "+table+"(id,conversation_id,tenant_id,role,"+column+",created_at) VALUES(?,?,'t1','user','synthetic-scope-input',UTC_TIMESTAMP(6))")){q.setString(1,message);q.setString(2,session);assertEquals(1,q.executeUpdate());}
    }
}

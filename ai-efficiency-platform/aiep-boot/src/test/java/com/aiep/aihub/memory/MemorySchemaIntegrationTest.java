package com.aiep.aihub.memory;

import com.aiep.aihub.repository.memory.MemoryMapper;
import com.baomidou.mybatisplus.extension.spring.MybatisSqlSessionFactoryBean;
import javax.crypto.Cipher;
import javax.crypto.AEADBadTagException;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.net.URI;
import java.security.SecureRandom;
import org.apache.ibatis.session.SqlSessionFactory;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.mybatis.spring.SqlSessionTemplate;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.sql.*;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import static org.junit.jupiter.api.Assertions.*;

/** 根runner预先审阅/应用DDL；测试不运行迁移、不回退共享配置。 */
@ActiveProfiles("memory-it")
@EnabledIfSystemProperty(named="memory.integration.enabled", matches="true")
@SpringJUnitConfig(MemorySchemaIntegrationTest.EmptyConfiguration.class)
class MemorySchemaIntegrationTest {
    @Configuration(proxyBeanMethods=false) static class EmptyConfiguration { }
    private String url, user, password;

    @Test void actualMySqlSchemaIsolationAndStateInvariants() throws Exception {
        url=required("MEMORY_IT_MYSQL_JDBC_URL");user=required("MEMORY_IT_MYSQL_USER");password=required("MEMORY_IT_MYSQL_PASSWORD");
        assertTrue(url.startsWith("jdbc:mysql://"), "只接受显式MySQL");
        URI parsed;
        try { parsed=URI.create(url.substring(5)); } catch(IllegalArgumentException invalid){throw new AssertionError("JDBC格式无效");}
        assertNull(parsed.getUserInfo(),"凭据不得嵌入URL");
        String schema=parsed.getPath().substring(1);
        assertTrue(schema.matches("aiep_memory_it_[0-9]{8}_[0-9a-f]{10}"),"禁止非专属库");
        try(Connection c=open()) {
            assertEquals("MySQL",c.getMetaData().getDatabaseProductName());
            assertEquals(schema,scalar(c,"SELECT DATABASE()"));
            long tables=number(c,"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name LIKE 'ai\\_memory\\_%'");
            if("rollback".equals(System.getProperty("memory.schema.phase"))) {
                assertEquals(0,tables);
                assertEquals(0,number(c,"SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema=DATABASE() AND trigger_name LIKE 'trg\\_memory\\_%'"));return;
            }
            // 空库首次执行在此真正缺表红，不以disabled/skip冒称红绿。
            assertEquals(12,tables,"需要审阅后的12对象；测试不自动建表");
            assertEquals(0,number(c,"SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name LIKE 'ai\\_memory\\_%' AND sub_part IS NOT NULL"));
            if("reauth-red".equals(System.getProperty("memory.schema.phase"))) { explicitReauthorization(c); return; }
            exactIdentityAndScope(c);
            closedCatalogIsByteExact(c);
            stateAndImmutability(c);
            sourceOutboxTombstone(c);
            transactionsAndCas(c);
            concurrentFirstCreation();
            mapperAndAad(c);
            explicitReauthorization(c);
        }
    }

    private void exactIdentityAndScope(Connection c) throws Exception {
        byte[] emoji=b("😀".repeat(128));assertEquals(512,emoji.length);
        item(c,emoji,emoji,"emoji", "operations","response.language");
        assertEquals(1,countItem(c,emoji,"emoji"));
        for(String tenant:List.of("tenant","tenant ")) for(String subject:List.of("user","user "))
            item(c,b(tenant),b(subject),"id-"+tenant.length()+"-"+subject.length(),"operations","response.language");
        assertEquals(1,countItem(c,b("tenant"),"id-6-4"));assertEquals(0,countItem(c,b("tenant "),"id-6-4"));
        item(c,b("tenant"),b("user"),"other-agent","hr","response.language");
        assertEquals(2,number(c,"SELECT COUNT(*) FROM ai_memory_item WHERE tenant_id=_binary'tenant' AND subject_id=_binary'user'"));
        execute(c,"INSERT INTO ai_memory_item(tenant_id,id,subject_id,owner_id,domain,origin_top_agent_id,scope_type,scope_id,field_key) VALUES (?,?,?,?,?,?,'PROJECT',?,?)",b("tenant"),b("project-scope"),b("user"),b("owner"),"operations","operations",b("project-1"),"response.language");
        assertEquals(3,number(c,"SELECT COUNT(*) FROM ai_memory_item WHERE tenant_id=_binary'tenant' AND subject_id=_binary'user'"));
        assertThrows(SQLException.class,()->execute(c,"INSERT INTO ai_memory_item (tenant_id,id,subject_id,owner_id,domain,origin_top_agent_id,scope_id,field_key) VALUES (?,?,?,?,?,?,?,?)",b("bad"),b("bad"),b("user"),b("owner"),"operations","operations",b("forged"),"response.language"));
    }

    private void closedCatalogIsByteExact(Connection c) throws Exception {
        int index=0;
        // 原始JDBC+原始scope编码故意绕过Java目录helper；每例独立tenant避免被其他唯一键碰巧拒绝。
        for(String[] pair:new String[][] {{"operations","operations "},{"operations ","operations"},
                {"Operations","operations"},{"operations","Operations"},{"hr","hr "},{"hr ","hr"},
                {"customer-service","customer-service "},{"customer-service ","customer-service"}}) {
            byte[] tenant=b("catalog-item-"+(index++));
            assertThrows(SQLException.class,()->execute(c,"INSERT INTO ai_memory_item(tenant_id,id,subject_id,owner_id,domain,origin_top_agent_id,scope_id,field_key) VALUES (?,?,?,?,?,?,?,?)",
                    tenant,b("item"),b("user"),b("owner"),pair[0],pair[1],scope(b("user"),pair[1]),"response.language"));
        }
        for(String bad:List.of("operations ","Operations","hr ","customer-service ")) {
            byte[] tenant=b("catalog-policy-"+(index++));
            assertThrows(SQLException.class,()->execute(c,"INSERT INTO ai_memory_policy(tenant_id,id,domain) VALUES (?,?,?)",tenant,b("policy"),bad));
        }
        for(String[] pair:new String[][] {{"operations","operations "},{"operations ","operations"},{"Operations","operations"}}) {
            byte[] tenant=b("catalog-binding-"+(index++));
            assertThrows(SQLException.class,()->execute(c,"INSERT INTO ai_memory_session_binding(tenant_id,id,user_id,domain,top_level_agent_id,session_id,original_object_type,original_object_id) VALUES (?,?,?,?,?,?,?,?)",
                    tenant,b("binding"),b("user"),pair[0],pair[1],b("session"),"OPERATION_CONVERSATION",b("session")));
        }
        for(String bad:List.of("USER_PRIVATE ","user_private","PROJECT ","project")) {
            byte[] tenant=b("catalog-scope-"+(index++));
            assertThrows(SQLException.class,()->execute(c,"INSERT INTO ai_memory_item(tenant_id,id,subject_id,owner_id,domain,origin_top_agent_id,scope_type,scope_id,field_key) VALUES (?,?,?,?,?,?,?,?,?)",
                    tenant,b("item"),b("user"),b("owner"),"operations","operations",bad,scope(b("user"),"operations"),"response.language"));
        }
        for(String[] pair:new String[][] {{"operations ","USER_PRIVATE"},{"Operations","USER_PRIVATE"},{"operations","USER_PRIVATE "},{"operations","user_private"}}) {
            byte[] tenant=b("catalog-suppression-"+(index++));
            assertThrows(SQLException.class,()->execute(c,"INSERT INTO ai_memory_suppression(tenant_id,id,subject_id,domain,scope_type,scope_id,field_key) VALUES (?,?,?,?,?,?,?)",
                    tenant,b("rule"),b("user"),pair[0],pair[1],scope(b("user"),"operations"),"response.language"));
        }
        // 每个合法目录仍接受规范scope；先前的128emoji/尾空格身份正向继续覆盖。
        for(String agent:List.of("operations","customer-service","hr")) {
            item(c,b("catalog-valid"),b("user"),agent,agent,"response.language");
        }
        assertEquals(3,number(c,"SELECT COUNT(*) FROM ai_memory_item WHERE tenant_id=_binary'catalog-valid'"));
    }

    private void stateAndImmutability(Connection c) throws Exception {
        byte[] tenant=b("state"); item(c,tenant,b("subject"),"item","operations","response.language");
        execute(c,"INSERT INTO ai_memory_policy(tenant_id,id,domain) VALUES (?,?,'operations')",tenant,b("policy"));
        execute(c,"INSERT INTO ai_memory_policy_version(tenant_id,policy_id,version_id,policy_json,content_hmac) VALUES (?,?,?,CAST('{}' AS JSON),?)",tenant,b("policy"),b("pv1"),new byte[32]);
        assertThrows(SQLException.class,()->execute(c,"UPDATE ai_memory_policy_version SET policy_json=CAST('{\"enabled\":true}' AS JSON) WHERE tenant_id=?",tenant));
        version(c,tenant,"item","v1","ACTIVE");
        execute(c,"UPDATE ai_memory_item SET current_version_id=? WHERE tenant_id=? AND id=?",b("v1"),tenant,b("item"));
        assertThrows(SQLException.class,()->version(c,tenant,"item","v2","ACTIVE"));
        version(c,tenant,"item","conflict","CONFLICTED");
        assertThrows(SQLException.class,()->execute(c,"UPDATE ai_memory_item SET current_version_id=? WHERE tenant_id=? AND id=?",b("conflict"),tenant,b("item")));
        assertThrows(SQLException.class,()->execute(c,"UPDATE ai_memory_version SET status='SUPERSEDED' WHERE tenant_id=? AND id=?",tenant,b("v1")));
        assertThrows(SQLException.class,()->execute(c,"UPDATE ai_memory_version SET encrypted_payload=? WHERE tenant_id=? AND id=?",b("overwrite"),tenant,b("v1")));
        assertThrows(SQLException.class,()->execute(c,"DELETE FROM ai_memory_version WHERE tenant_id=? AND id=?",tenant,b("conflict")));
        execute(c,"UPDATE ai_memory_item SET current_version_id=NULL WHERE tenant_id=? AND id=?",tenant,b("item"));
        execute(c,"UPDATE ai_memory_version SET status='SUPERSEDED' WHERE tenant_id=? AND id=?",tenant,b("v1"));
        version(c,tenant,"item","v2","ACTIVE");
        execute(c,"UPDATE ai_memory_item SET current_version_id=? WHERE tenant_id=? AND id=?",b("v2"),tenant,b("item"));
        assertThrows(SQLException.class,()->execute(c,"UPDATE ai_memory_version SET status='DELETED',deletion_epoch=1,encrypted_payload=NULL,nonce=NULL,auth_tag=NULL,content_hmac=NULL,scrubbed_at=UTC_TIMESTAMP(6) WHERE tenant_id=? AND id=?",tenant,b("v1")));
        execute(c,"INSERT INTO ai_memory_deletion_job(tenant_id,id,item_id,deletion_epoch,status,required_targets,completed_targets) VALUES (?,?,?,1,'SUCCEEDED',1,1)",tenant,b("delete"),b("item"));
        execute(c,"UPDATE ai_memory_version SET status='DELETED',deletion_epoch=1,encrypted_payload=NULL,nonce=NULL,auth_tag=NULL,content_hmac=NULL,scrubbed_at=UTC_TIMESTAMP(6) WHERE tenant_id=? AND id=?",tenant,b("v1"));
        assertThrows(SQLException.class,()->execute(c,"UPDATE ai_memory_version SET encrypted_payload=? WHERE tenant_id=? AND id=?",b("revive"),tenant,b("v1")));
        assertEquals("key-1",scalar(c,"SELECT key_version FROM ai_memory_version WHERE tenant_id=_binary'state' AND id=_binary'v1'"));
        assertEquals("state",scalar(c,"SELECT CONVERT(aad_tenant_id USING utf8mb4) FROM ai_memory_version WHERE tenant_id=_binary'state' AND id=_binary'v2'"));
        assertThrows(SQLException.class,()->execute(c,"UPDATE ai_memory_version SET aad_version_id=? WHERE tenant_id=? AND id=?",b("wrong"),tenant,b("v2")));
    }

    private void sourceOutboxTombstone(Connection c) throws Exception {
        execute(c,"INSERT INTO ai_memory_source(tenant_id,id,source_type,source_object_ref,source_version) VALUES (?,?,?,?,?)",b("state"),b("source"),"MESSAGE",b("message"),b("1"));
        execute(c,"INSERT INTO ai_memory_dependency(tenant_id,source_id,target_type,target_id,target_version) VALUES (?,?,?,?,?)",b("state"),b("source"),"MEMORY_VERSION",b("item"),b("v2"));
        assertEquals(1,number(c,"SELECT COUNT(*) FROM ai_memory_dependency WHERE tenant_id=_binary'state' AND source_id=_binary'source'"));
        assertThrows(SQLException.class,()->execute(c,"UPDATE ai_memory_source SET source_epoch=0 WHERE tenant_id=? AND id=?",b("state"),b("source")));
        execute(c,"INSERT INTO ai_memory_outbox(tenant_id,event_id,aggregate_id,version_id,event_type,deletion_epoch) VALUES (?,?,?,?,?,?)",b("state"),b("event"),b("item"),b("v2"),"INVALIDATE",1);
        assertThrows(SQLException.class,()->execute(c,"INSERT INTO ai_memory_outbox(tenant_id,event_id,aggregate_id,version_id,event_type,deletion_epoch) VALUES (?,?,?,?,?,?)",b("state"),b("event-other"),b("item"),b("v2"),"INVALIDATE",1));
        execute(c,"INSERT INTO ai_memory_tombstone(tenant_id,target_type,target_id,deletion_epoch) VALUES (?,?,?,2)",b("state"),"ITEM",b("item"));
        assertThrows(SQLException.class,()->execute(c,"UPDATE ai_memory_tombstone SET deletion_epoch=1 WHERE tenant_id=?",b("state")));
        assertThrows(SQLException.class,()->execute(c,"DELETE FROM ai_memory_tombstone WHERE tenant_id=?",b("state")));
    }

    private void transactionsAndCas(Connection c) throws Exception {
        assertEquals(1,execute(c,"UPDATE ai_memory_item SET revision=revision+1 WHERE tenant_id=? AND id=? AND revision=0",b("state"),b("item")));
        assertEquals(0,execute(c,"UPDATE ai_memory_item SET revision=revision+1 WHERE tenant_id=? AND id=? AND revision=0",b("state"),b("item")));
        c.setAutoCommit(false);
        try { item(c,b("rollback"),b("user"),"rollback","operations","response.language");c.rollback(); }
        finally { c.setAutoCommit(true); }
        assertEquals(0,countItem(c,b("rollback"),"rollback"));
    }

    private void concurrentFirstCreation() throws Exception {
        ExecutorService executor=Executors.newFixedThreadPool(2);
        CountDownLatch ready=new CountDownLatch(2),go=new CountDownLatch(1);
        try {
            List<Future<Boolean>> results=new ArrayList<>();
            for(String id:List.of("a","b")) results.add(executor.submit(()->{
                try(Connection c=open()){ready.countDown();go.await();
                    c.setAutoCommit(false);
                    try {
                        item(c,b("concurrent"),b("user"),id,"operations","response.language");
                        version(c,b("concurrent"),id,"v-"+id,"ACTIVE");
                        execute(c,"UPDATE ai_memory_item SET current_version_id=? WHERE tenant_id=? AND id=?",b("v-"+id),b("concurrent"),b(id));
                        c.commit();return true;
                    } catch(SQLIntegrityConstraintViolationException duplicate){c.rollback();return false;}
                }
            }));
            assertTrue(ready.await(5,TimeUnit.SECONDS));go.countDown();
            int winners=0;for(Future<Boolean> result:results)if(result.get(10,TimeUnit.SECONDS))winners++;
            assertEquals(1,winners);
            try(Connection c=open()) {assertEquals(1,number(c,"SELECT COUNT(*) FROM ai_memory_version WHERE tenant_id=_binary'concurrent' AND status='ACTIVE'"));}
        } finally {go.countDown();executor.shutdownNow();}
    }

    private void mapperAndAad(Connection c) throws Exception {
        assertEquals(512,MemoryMapper.identity("😀".repeat(128)).length);
        assertArrayEquals(b("user "),MemoryMapper.identity("user "));
        assertThrows(IllegalArgumentException.class,()->MemoryMapper.identity("😀".repeat(129)));
        assertTrue(MemoryMapper.privateScope("😀".repeat(128),"customer-service").length>512);
        assertArrayEquals(scope(b("subject"),"operations"),MemoryMapper.privateScope("subject","operations"));
        DriverManagerDataSource ds=new DriverManagerDataSource(url,user,password);
        MybatisSqlSessionFactoryBean bean=new MybatisSqlSessionFactoryBean();bean.setDataSource(ds);
        com.baomidou.mybatisplus.core.MybatisConfiguration config=new com.baomidou.mybatisplus.core.MybatisConfiguration();
        config.setMapUnderscoreToCamelCase(true);config.setArgNameBasedConstructorAutoMapping(true);bean.setConfiguration(config);
        bean.setMapperLocations(new ClassPathResource("mapper/memory/MemoryMapper.xml"));
        SqlSessionFactory factory=bean.getObject();assertNotNull(factory);
        byte[] tenant=b("mapper"),item=b("mapper-item"),version=b("mapper-version");
        byte[] key=new byte[32],nonce=new byte[12];new SecureRandom().nextBytes(key);new SecureRandom().nextBytes(nonce);
        byte[] aad=MemoryMapper.aad(tenant,item,version,"key-1");
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE,new SecretKeySpec(key,"AES"),new GCMParameterSpec(128,nonce));cipher.updateAAD(aad);
        byte[] encrypted=cipher.doFinal(b("synthetic-value"));
        for(byte[] wrong:new byte[][] {MemoryMapper.aad(b("other"),item,version,"key-1"),MemoryMapper.aad(tenant,b("other"),version,"key-1"),MemoryMapper.aad(tenant,item,b("other"),"key-1"),MemoryMapper.aad(tenant,item,version,"key-2")}) {
            Cipher decrypt=Cipher.getInstance("AES/GCM/NoPadding");decrypt.init(Cipher.DECRYPT_MODE,new SecretKeySpec(key,"AES"),new GCMParameterSpec(128,nonce));decrypt.updateAAD(wrong);
            assertThrows(AEADBadTagException.class,()->decrypt.doFinal(encrypted));
        }
        // 与生产SpringManagedTransactionFactory一致，由同一DataSource事务管理器控制连接。
        SqlSessionTemplate sessions=new SqlSessionTemplate(factory);
        TransactionTemplate transactions=new TransactionTemplate(new DataSourceTransactionManager(ds));
        transactions.executeWithoutResult(transaction -> {
            MemoryMapper mapper=sessions.getMapper(MemoryMapper.class);
            var row=new MemoryMapper.MemoryItemPO(tenant,item,"USER",b("subject"),b("distinct-owner"),"operations","operations","USER_PRIVATE",MemoryMapper.privateScope("subject","operations"),"assistant_response","response.language","LIVE",0,null,0,0,0);
            assertEquals(1,mapper.insertItem(row));
            var found=mapper.findItemForUpdate(tenant,item);assertArrayEquals(b("distinct-owner"),found.ownerId());assertArrayEquals(b("subject"),found.subjectId());
            assertNull(mapper.findItemForUpdate(b("other-tenant"),item));
            assertEquals(1,mapper.insertVersion(new MemoryMapper.MemoryVersionPO(tenant,item,version,"ACTIVE",Arrays.copyOf(encrypted,encrypted.length-16),"key-1",nonce,Arrays.copyOfRange(encrypted,encrypted.length-16,encrypted.length),new byte[32],"memory-value/1",null,null,null)));
            assertEquals(1,mapper.compareAndSetCurrent(tenant,item,0,version,"LIVE"));
            assertEquals(0,mapper.compareAndSetCurrent(tenant,item,0,version,"LIVE"));
            assertEquals(1,mapper.findDependents(b("state"),b("source")).size());
            assertEquals(1,mapper.insertOutbox(tenant,b("mapper-event"),item,version,"INVALIDATE",0));
            mapper.advanceTombstone(tenant,"ITEM",item,2,2,2);mapper.advanceTombstone(tenant,"ITEM",item,1,1,1);
        });
        assertEquals(1,countItem(c,tenant,"mapper-item"));
        assertEquals(2,number(c,"SELECT deletion_epoch FROM ai_memory_tombstone WHERE tenant_id=_binary'mapper'"));
        transactions.executeWithoutResult(transaction -> {
            var row=new MemoryMapper.MemoryItemPO(tenant,b("mapper-rollback"),"USER",b("subject"),b("owner"),"operations","operations","USER_PRIVATE",MemoryMapper.privateScope("subject","operations"),"assistant_response","response.length","LIVE",0,null,0,0,0);
            sessions.getMapper(MemoryMapper.class).insertItem(row);
            transaction.setRollbackOnly();
        });
        assertEquals(0,countItem(c,tenant,"mapper-rollback"));
    }

    private void explicitReauthorization(Connection c) throws Exception {
        boolean expectedSuppressionField=number(c,"SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='ai_memory_decision' AND column_name='expected_suppression_revision'")==1;
        if("reauth-red".equals(System.getProperty("memory.schema.phase"))) assertFalse(expectedSuppressionField,"红阶段必须使用旧已审DDL");
        else assertTrue(expectedSuppressionField,"重新授权必须持久化expected suppression revision");
        byte[] tenant=b("reauth");
        item(c,tenant,b("subject"),"anchor","operations","response.language");
        version(c,tenant,"anchor","old","ACTIVE");
        execute(c,"UPDATE ai_memory_item SET current_version_id=? WHERE tenant_id=? AND id=?",b("old"),tenant,b("anchor"));
        execute(c,"UPDATE ai_memory_item SET current_version_id=NULL,lifecycle='DELETE_PENDING',revision=1,grant_epoch=1,source_epoch=1,deletion_epoch=1 WHERE tenant_id=? AND id=?",tenant,b("anchor"));
        execute(c,"INSERT INTO ai_memory_deletion_job(tenant_id,id,item_id,deletion_epoch,status,required_targets,completed_targets) VALUES (?,?,?,1,'SUCCEEDED',1,1)",tenant,b("completed-delete"),b("anchor"));
        execute(c,"UPDATE ai_memory_version SET status='DELETED',grant_epoch=1,source_epoch=1,deletion_epoch=1,encrypted_payload=NULL,nonce=NULL,auth_tag=NULL,content_hmac=NULL,scrubbed_at=UTC_TIMESTAMP(6) WHERE tenant_id=? AND id=?",tenant,b("old"));
        execute(c,"UPDATE ai_memory_item SET lifecycle='DELETED' WHERE tenant_id=? AND id=?",tenant,b("anchor"));
        execute(c,"INSERT INTO ai_memory_suppression(tenant_id,id,subject_id,domain,scope_type,scope_id,purpose,field_key,epoch,active) VALUES (?,?,?,'operations','USER_PRIVATE',?,'assistant_response','response.language',5,TRUE)",tenant,b("field-rule"),b("subject"),scope(b("subject"),"operations"));
        // 旧版本来源仍被SOURCE抑制；新用户输入的新值不得被旧依赖全局阻断。
        execute(c,"INSERT INTO ai_memory_source(tenant_id,id,source_type,source_object_ref,source_version) VALUES (?,?, 'MESSAGE',?,?)",tenant,b("old-source"),b("old-message"),b("1"));
        execute(c,"INSERT INTO ai_memory_dependency(tenant_id,source_id,target_type,target_id,target_version) VALUES (?,?,'MEMORY_VERSION',?,?)",tenant,b("old-source"),b("anchor"),b("old"));
        execute(c,"INSERT INTO ai_memory_suppression(tenant_id,id,subject_id,domain,scope_type,scope_id,purpose,field_key,suppression_kind,source_id,source_version,epoch,active) VALUES (?,?,?,'operations','USER_PRIVATE',?,'assistant_response','','SOURCE',?,?,3,TRUE)",tenant,b("old-source-rule"),b("subject"),scope(b("subject"),"operations"),b("old-source"),b("1"));
        for(String rejected:List.of("NO_DECISION","STILL_SUPPRESSED","BAD_REVISION","NO_GRANT_ADVANCE","BAD_ACTOR","NON_USER","ORDINARY_SAVE","ZERO_WITH_RULE","MISSING_SUPPRESSION_REVISION","BAD_SUPPRESSION_REVISION","SOURCE_REGRESSION","WRONG_VERSION","NEW_SOURCE_SUPPRESSED")) {
            c.setAutoCommit(false);
            try {
                reauthorizationCandidate(c,rejected,expectedSuppressionField);
                SQLException failure=assertThrows(SQLException.class,()->reactivateAnchor(c,rejected),"未满足显式人类重新授权不得解锁");
                assertEquals("45000",failure.getSQLState());
            } finally { c.rollback(); c.setAutoCommit(true); }
        }
        c.setAutoCommit(false);
        try {
            reauthorizationCandidate(c,"VALID",expectedSuppressionField);
            try { assertEquals(1,reactivateAnchor(c,"VALID")); }
            catch(SQLException blocked) { fail("MEMORY_REAUTHORIZE_POSITIVE_BLOCKED sqlstate="+blocked.getSQLState()+" "+blocked.getMessage(),blocked); }
            c.commit();
        } finally { c.rollback(); c.setAutoCommit(true); }
        assertEquals(0,reactivateAnchor(c,"VALID"),"原revision只能CAS成功一次");
        assertEquals("LIVE",scalar(c,"SELECT lifecycle FROM ai_memory_item WHERE tenant_id=_binary'reauth' AND id=_binary'anchor'"));
        assertEquals(1,number(c,"SELECT COUNT(*) FROM ai_memory_item WHERE tenant_id=_binary'reauth' AND id=_binary'anchor' AND revision=2 AND grant_epoch=2 AND source_epoch=1 AND deletion_epoch=1 AND current_version_id=_binary'new'"));
        assertEquals(1,number(c,"SELECT COUNT(*) FROM ai_memory_version WHERE tenant_id=_binary'reauth' AND id=_binary'old' AND status='DELETED' AND encrypted_payload IS NULL AND nonce IS NULL AND auth_tag IS NULL AND content_hmac IS NULL"));
        assertThrows(SQLException.class,()->execute(c,"UPDATE ai_memory_version SET status='ACTIVE' WHERE tenant_id=? AND id=?",tenant,b("old")));
        assertEquals(1,number(c,"SELECT COUNT(*) FROM ai_memory_version WHERE tenant_id=_binary'reauth' AND item_id=_binary'anchor' AND status='ACTIVE'"));
        assertEquals(1,number(c,"SELECT COUNT(*) FROM ai_memory_suppression WHERE tenant_id=_binary'reauth' AND id=_binary'old-source-rule' AND active=TRUE AND epoch=3"),"旧来源抑制不得被字段重新授权解除");
        reauthorizationWithoutSuppression(c);
    }

    private void reauthorizationCandidate(Connection c,String scenario,boolean expectedField) throws Exception {
        reauthorizationCandidate(c,scenario,expectedField,b("reauth"),true);
    }
    private void reauthorizationCandidate(Connection c,String scenario,boolean expectedField,byte[] tenant,boolean hasRule) throws Exception {
        boolean decision=!"NO_DECISION".equals(scenario);
        if(decision) {
            execute(c,"INSERT INTO ai_memory_decision(tenant_id,id,item_id,target_version_id,actor_id,actor_kind,decision_type,request_id,expected_revision,resulting_revision) VALUES (?,?,?,?,?,?,'REAUTHORIZE',?,?,2)",
                    tenant,b("allow"),b("anchor"),b("WRONG_VERSION".equals(scenario)?"other-version":"new"),b("BAD_ACTOR".equals(scenario)?"subject":"owner"),"NON_USER".equals(scenario)?"SYSTEM":"USER",b("explicit-allow"),"BAD_REVISION".equals(scenario)?0:1);
            if("ORDINARY_SAVE".equals(scenario)) execute(c,"UPDATE ai_memory_decision SET decision_type='SAVE' WHERE tenant_id=? AND id=?",tenant,b("allow"));
            long expectedSuppression="ZERO_WITH_RULE".equals(scenario)?0:(!hasRule?0:("BAD_SUPPRESSION_REVISION".equals(scenario)?4:5));
            if(expectedField && !"MISSING_SUPPRESSION_REVISION".equals(scenario)) execute(c,"UPDATE ai_memory_decision SET expected_suppression_revision=? WHERE tenant_id=? AND id=?",expectedSuppression,tenant,b("allow"));
        }
        if(hasRule && !"STILL_SUPPRESSED".equals(scenario)) assertEquals(1,execute(c,"UPDATE ai_memory_suppression SET active=FALSE,epoch=epoch+1 WHERE tenant_id=? AND id=? AND active=TRUE AND epoch=5",tenant,b("field-rule")));
        execute(c,"INSERT INTO ai_memory_version(tenant_id,item_id,id,status,encrypted_payload,key_version,nonce,auth_tag,content_hmac,aad_tenant_id,aad_item_id,aad_version_id,aad_key_version,decision_id,grant_epoch,source_epoch,deletion_epoch) VALUES (?,?,?,'ACTIVE',?,?,?,?,?,?,?,?,?,?,?,1,1)",
                tenant,b("anchor"),b("new"),b("new-synthetic-cipher"),"key-1",new byte[12],new byte[16],new byte[32],tenant,b("anchor"),b("new"),"key-1",decision?b("allow"):null,"NO_GRANT_ADVANCE".equals(scenario)?1:2);
        if("NEW_SOURCE_SUPPRESSED".equals(scenario)) execute(c,"INSERT INTO ai_memory_dependency(tenant_id,source_id,target_type,target_id,target_version) VALUES (?,?,'MEMORY_VERSION',?,?)",tenant,b("old-source"),b("anchor"),b("new"));
    }
    private int reactivateAnchor(Connection c,String scenario) throws SQLException {
        return reactivateAnchor(c,scenario,b("reauth"));
    }
    private int reactivateAnchor(Connection c,String scenario,byte[] tenant) throws SQLException {
        return execute(c,"UPDATE ai_memory_item SET lifecycle='LIVE',current_version_id=?,revision=2,grant_epoch=?,source_epoch=?,deletion_epoch=1 WHERE tenant_id=? AND id=? AND revision=1",
                b("new"),"NO_GRANT_ADVANCE".equals(scenario)?1:2,"SOURCE_REGRESSION".equals(scenario)?0:1,tenant,b("anchor"));
    }

    private void reauthorizationWithoutSuppression(Connection c) throws Exception {
        byte[] tenant=b("reauth-no-field-rule");
        item(c,tenant,b("subject"),"anchor","operations","response.language");
        version(c,tenant,"anchor","old","ACTIVE");
        execute(c,"UPDATE ai_memory_item SET lifecycle='DELETE_PENDING',revision=1,grant_epoch=1,source_epoch=1,deletion_epoch=1 WHERE tenant_id=? AND id=?",tenant,b("anchor"));
        execute(c,"INSERT INTO ai_memory_deletion_job(tenant_id,id,item_id,deletion_epoch,status,required_targets,completed_targets) VALUES (?,?,?,1,'SUCCEEDED',1,1)",tenant,b("delete-only"),b("anchor"));
        execute(c,"UPDATE ai_memory_version SET status='DELETED',grant_epoch=1,source_epoch=1,deletion_epoch=1,encrypted_payload=NULL,nonce=NULL,auth_tag=NULL,content_hmac=NULL,scrubbed_at=UTC_TIMESTAMP(6) WHERE tenant_id=? AND id=?",tenant,b("old"));
        execute(c,"UPDATE ai_memory_item SET lifecycle='DELETED' WHERE tenant_id=? AND id=?",tenant,b("anchor"));
        assertEquals(0,number(c,"SELECT COUNT(*) FROM ai_memory_suppression WHERE tenant_id=_binary'reauth-no-field-rule'"));
        c.setAutoCommit(false);
        try {
            reauthorizationCandidate(c,"NO_DECISION",true,tenant,false);
            assertThrows(SQLException.class,()->reactivateAnchor(c,"NO_DECISION",tenant));
        } finally { c.rollback();c.setAutoCommit(true); }
        c.setAutoCommit(false);
        try {
            reauthorizationCandidate(c,"VALID",true,tenant,false);
            assertEquals(1,reactivateAnchor(c,"VALID",tenant),"expected suppression revision=0只表示完整字段规则不存在，仍需人类重新授权");
            c.commit();
        } finally { c.rollback();c.setAutoCommit(true); }
        assertEquals(0,reactivateAnchor(c,"VALID",tenant));
        assertEquals(1,number(c,"SELECT COUNT(*) FROM ai_memory_version WHERE tenant_id=_binary'reauth-no-field-rule' AND id=_binary'old' AND status='DELETED' AND encrypted_payload IS NULL"));
    }

    private void item(Connection c,byte[] tenant,byte[] subject,String id,String domain,String field) throws Exception {
        execute(c,"INSERT INTO ai_memory_item(tenant_id,id,subject_id,owner_id,domain,origin_top_agent_id,scope_id,field_key) VALUES (?,?,?,?,?,?,?,?)",tenant,b(id),subject,b("owner"),domain,domain,scope(subject,domain),field);
    }
    private void version(Connection c,byte[] tenant,String item,String id,String status) throws Exception {
        execute(c,"INSERT INTO ai_memory_version(tenant_id,item_id,id,status,encrypted_payload,key_version,nonce,auth_tag,content_hmac,aad_tenant_id,aad_item_id,aad_version_id,aad_key_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",tenant,b(item),b(id),status,b("synthetic-ciphertext-"+id),"key-1",new byte[12],new byte[16],new byte[32],tenant,b(item),b(id),"key-1");
    }
    private long countItem(Connection c,byte[] tenant,String id) throws Exception {try(PreparedStatement s=c.prepareStatement("SELECT COUNT(*) FROM ai_memory_item WHERE tenant_id=? AND id=?")){s.setBytes(1,tenant);s.setBytes(2,b(id));try(ResultSet r=s.executeQuery()){r.next();return r.getLong(1);}}}
    private Connection open() throws SQLException {return DriverManager.getConnection(url,user,password);}
    private static byte[] b(String value){return value.getBytes(StandardCharsets.UTF_8);}
    private static byte[] scope(byte[] subject,String agent){byte[] a=b(agent);return ByteBuffer.allocate(8+subject.length+a.length).put(b("up1:")).putInt(subject.length).put(subject).put(a).array();}
    private static String required(String key){String value=System.getenv(key);assertTrue(value!=null&&!value.isBlank(),key+"必须显式提供");return value;}
    private static int execute(Connection c,String sql,Object... values)throws SQLException{try(PreparedStatement s=c.prepareStatement(sql)){for(int i=0;i<values.length;i++)s.setObject(i+1,values[i]);return s.executeUpdate();}}
    private static String scalar(Connection c,String sql)throws SQLException{try(Statement s=c.createStatement();ResultSet r=s.executeQuery(sql)){assertTrue(r.next());return r.getString(1);}}
    private static long number(Connection c,String sql)throws SQLException{return Long.parseLong(scalar(c,sql));}
}

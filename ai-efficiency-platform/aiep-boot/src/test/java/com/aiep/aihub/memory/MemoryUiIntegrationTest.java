package com.aiep.aihub.memory;

import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.facade.memory.DefaultMemoryFacade;
import com.aiep.aihub.repository.memory.*;
import com.aiep.aihub.web.memory.*;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.identity.facade.DatabaseIdentityFacade;
import com.aiep.identity.repository.IdentitySessionMapper;
import com.aiep.platformcore.config.TraceIdFilter;
import com.baomidou.mybatisplus.autoconfigure.MybatisPlusAutoConfiguration;
import com.baomidou.mybatisplus.extension.spring.MybatisSqlSessionFactoryBean;
import java.net.ServerSocket;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.TimeUnit;
import javax.sql.DataSource;
import org.apache.ibatis.session.SqlSessionFactory;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.annotation.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.*;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.web.bind.annotation.*;
import static org.junit.jupiter.api.Assertions.*;
import static com.aiep.aihub.memory.MemoryPreferenceIntegrationTest.*;

/** 显式隔离浏览器→生产Java→真实MySQL；不启动Agent、模型或伪造清理确认。 */
@EnabledIfSystemProperty(named="memory.integration.enabled",matches="true")
class MemoryUiIntegrationTest {
    @Configuration(proxyBeanMethods=false)
    @EnableAutoConfiguration(exclude={DataSourceAutoConfiguration.class,MybatisPlusAutoConfiguration.class},excludeName={
        "org.redisson.spring.starter.RedissonAutoConfigurationV2","org.springframework.boot.autoconfigure.data.redis.RedisAutoConfiguration","org.springframework.boot.autoconfigure.data.redis.RedisRepositoriesAutoConfiguration"})
    @EnableTransactionManagement
    @Import({ConversationScopeResolver.class,MemoryScopePolicy.class,MemorySessionBindingService.class,MemoryPolicyService.class,MemoryVersionService.class,MemoryPreferenceService.class,DefaultMemoryFacade.class,
        MemoryActorResolver.class,MemoryController.class,MemoryExceptionHandler.class,TraceIdFilter.class,MemoryForgetService.class,MemorySuppressionService.class,MemoryDeletionService.class,MemorySourceInvalidationService.class,MemoryDeletionController.class,MemoryDeletionExceptionHandler.class,RevokeFixture.class})
    static class ITConfiguration {
        @Bean DataSource dataSource(){return new DriverManagerDataSource(required("MEMORY_IT_MYSQL_JDBC_URL"),required("MEMORY_IT_MYSQL_USER"),required("MEMORY_IT_MYSQL_PASSWORD"));}
        @Bean PlatformTransactionManager transactionManager(DataSource ds){return new DataSourceTransactionManager(ds);}
        @Bean SqlSessionFactory sqlSessionFactory(DataSource ds)throws Exception{
            var factory=new MybatisSqlSessionFactoryBean();factory.setDataSource(ds);
            factory.setMapperLocations(new ClassPathResource("mapper/memory/MemoryMapper.xml"),new ClassPathResource("mapper/memory/MemoryForgetMapper.xml"),new ClassPathResource("mapper/identity/IdentitySessionMapper.xml"));
            var configuration=new com.baomidou.mybatisplus.core.MybatisConfiguration();configuration.setMapUnderscoreToCamelCase(true);factory.setConfiguration(configuration);return factory.getObject();
        }
        @Bean MemoryMapper memories(SqlSessionFactory factory){return new SqlSessionTemplate(factory).getMapper(MemoryMapper.class);}
        @Bean MemoryForgetMapper forgets(SqlSessionFactory factory){return new SqlSessionTemplate(factory).getMapper(MemoryForgetMapper.class);}
        @Bean IdentitySessionMapper identityMapper(SqlSessionFactory factory){return new SqlSessionTemplate(factory).getMapper(IdentitySessionMapper.class);}
        @Bean IdentityFacade identity(IdentitySessionMapper mapper){return new DatabaseIdentityFacade(mapper);}
        @Bean JdbcTemplate jdbc(DataSource ds){return new JdbcTemplate(ds);}
        @Bean MemoryValueCodec codec(){return new MemoryValueCodec("it","{\"it\":\""+Base64.getEncoder().encodeToString(random(32))+"\"}",Base64.getEncoder().encodeToString(random(32)));}
    }

    /** 仅本机临时验收装配；产品无此控制接口，调用者只能撤销自己当前登录。 */
    @RestController
    static class RevokeFixture {
        private final IdentityFacade identity;private final JdbcTemplate jdbc;
        RevokeFixture(IdentityFacade identity,JdbcTemplate jdbc){this.identity=identity;this.jdbc=jdbc;}
        @PostMapping("/__memory-ui/revoke")
        Map<String,Boolean> revoke(@RequestHeader("Authorization")String bearer)throws Exception{
            if(!bearer.startsWith("Bearer "))throw new org.springframework.web.server.ResponseStatusException(org.springframework.http.HttpStatus.UNAUTHORIZED);
            String credential=bearer.substring(7);var actor=identity.authenticate(credential).orElseThrow(()->new org.springframework.web.server.ResponseStatusException(org.springframework.http.HttpStatus.UNAUTHORIZED));
            String hash=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(credential.getBytes(StandardCharsets.UTF_8)));
            if(!hash.equals(actor.sessionRef()))throw new IllegalStateException("fixture identity binding mismatch");
            assertEquals(1,jdbc.update("UPDATE id_hr_session SET revoked_at=NOW(6) WHERE credential_hash=? AND tenant_id=? AND user_id=? AND revoked_at IS NULL",hash,actor.tenantId(),actor.userId()));
            return Map.of("revoked",true);
        }
    }

    @Test void actualBrowserActionsPersistAndRevokeAgainstRealJavaDatabase()throws Exception{
        var ds=checkedDataSource();
        try(var connection=ds.getConnection()){
            sourceTable(connection,"V1.0.0__operation_assistant_mvp.sql","ai_operation_conversation");
            sourceTable(connection,"V1.1.0__customer_service_knowledge_aihub.sql","ai_customer_service_conversation");
            sourceTable(connection,"V1.2.3__hr_execution_identity_and_sources.sql","id_hr_session");
            sourceTable(connection,"V1.2.3__hr_execution_identity_and_sources.sql","id_hr_grant");seed(connection);
        }
        var application=new SpringApplication(ITConfiguration.class);
        application.setDefaultProperties(Map.of("spring.config.location","optional:classpath:/memory-it-no-shared-config/","server.address","127.0.0.1","server.port","0","spring.main.banner-mode","off","logging.level.root","WARN","spring.jmx.enabled","false"));
        try(var context=(ServletWebServerApplicationContext)application.run("--spring.config.location=optional:classpath:/memory-it-no-shared-config/","--server.address=127.0.0.1","--server.port=0")){
            Path root=Path.of(System.getProperty("user.dir")).toAbsolutePath();while(root!=null&&!Files.isDirectory(root.resolve("ai-efficiency-platform-ui")))root=root.getParent();assertNotNull(root);
            int uiPort;try(var available=new ServerSocket(0,0,java.net.InetAddress.getLoopbackAddress())){uiPort=available.getLocalPort();}
            var builder=new ProcessBuilder("cmd.exe","/d","/c","pnpm.cmd","exec","playwright","test","--config","playwright.memory-api.config.ts");
            builder.directory(root.resolve("ai-efficiency-platform-ui").toFile()).redirectErrorStream(true).redirectOutput(root.resolve(".local-acceptance/agent-memory-implementation/logs/D14API-real-browser.log").toFile());
            var env=builder.environment();env.keySet().removeIf(key->key.contains("API_KEY")||key.contains("TOKEN")||key.contains("BASE_URL"));
            env.put("MEMORY_UI_INTEGRATION_ENABLED","1");env.put("MEMORY_UI_API_BASE_URL","http://127.0.0.1:"+context.getWebServer().getPort());env.put("MEMORY_UI_PORT",Integer.toString(uiPort));
            env.put("MEMORY_UI_ACCESS_TOKEN",TOKENS.get("t1:u1"));env.put("MEMORY_UI_OTHER_ACCESS_TOKEN",TOKENS.get("t1:u2"));
            env.put("MEMORY_UI_OPERATIONS_SESSION_ID",SESSIONS.get("t1:u1:operations:1"));env.put("MEMORY_UI_OPERATIONS_NEW_SESSION_ID",SESSIONS.get("t1:u1:operations:2"));
            env.put("MEMORY_UI_CUSTOMER_SERVICE_SESSION_ID",SESSIONS.get("t1:u1:customer-service:1"));env.put("MEMORY_UI_CUSTOMER_SERVICE_NEW_SESSION_ID",SESSIONS.get("t1:u1:customer-service:2"));
            var browser=builder.start();var owned=new LinkedHashMap<Long,ProcessHandle>();
            try{
                long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(240);
                while(browser.isAlive()&&System.nanoTime()<deadline){captureOwned(browser.toHandle(),owned);browser.waitFor(100,TimeUnit.MILLISECONDS);}
                assertFalse(browser.isAlive(),"actual browser test exceeded bounded deadline");
                assertEquals(0,browser.exitValue(),"actual browser test failed; inspect safe acceptance log");
            }finally{stopOwnedBrowser(browser,owned);}
            var jdbc=new JdbcTemplate(ds);
            assertTrue(jdbc.queryForObject("SELECT COUNT(*) FROM ai_memory_version",Integer.class)>=6);
            assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM ai_memory_item WHERE lifecycle='LIVE' AND current_version_id IS NULL",Integer.class));
            assertTrue(jdbc.queryForObject("SELECT COUNT(*) FROM ai_memory_deletion_job WHERE status<>'SUCCEEDED'",Integer.class)>0,"no worker or external ACK is fabricated");
            assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM id_hr_session WHERE credential_hash=? AND revoked_at IS NOT NULL",Integer.class,HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(TOKENS.get("t1:u1").getBytes(StandardCharsets.UTF_8)))));
        }
    }

    static void stopOwnedBrowser(Process browser)throws InterruptedException{
        stopOwnedBrowser(browser,new LinkedHashMap<>());
    }
    private static void captureOwned(ProcessHandle root,Map<Long,ProcessHandle> owned){
        owned.putIfAbsent(root.pid(),root);
        if(root.isAlive())root.descendants().forEach(child->owned.putIfAbsent(child.pid(),child));
    }
    private static void stopOwnedBrowser(Process browser,Map<Long,ProcessHandle> owned)throws InterruptedException{
        captureOwned(browser.toHandle(),owned);
        long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(10);
        while(owned.values().stream().anyMatch(ProcessHandle::isAlive)&&System.nanoTime()<deadline){
            for(var handle:new ArrayList<>(owned.values()))if(handle.isAlive())captureOwned(handle,owned);
            var children=new ArrayList<>(owned.values());Collections.reverse(children);
            for(var handle:children)if(handle.isAlive())handle.destroyForcibly();
            Thread.sleep(20);
        }
        if(owned.values().stream().anyMatch(ProcessHandle::isAlive))throw new IllegalStateException("owned acceptance process tree did not stop");
    }
}

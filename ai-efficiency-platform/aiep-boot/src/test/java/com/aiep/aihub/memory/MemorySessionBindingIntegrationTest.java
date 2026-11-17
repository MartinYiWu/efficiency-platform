package com.aiep.aihub.memory;

import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.application.memory.ConversationScopeResolver;
import com.aiep.aihub.application.memory.MemoryActorProvider;
import com.aiep.aihub.application.memory.MemoryScopePolicy;
import com.aiep.aihub.application.memory.MemorySessionBindingService;
import com.aiep.aihub.application.operation.OperationActor;
import com.aiep.aihub.repository.memory.MemoryMapper;
import com.aiep.identity.api.IdentityFacade;
import com.baomidou.mybatisplus.extension.spring.MybatisSqlSessionFactoryBean;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.apache.ibatis.executor.Executor;
import org.apache.ibatis.mapping.MappedStatement;
import org.apache.ibatis.plugin.Interceptor;
import org.apache.ibatis.plugin.Intercepts;
import org.apache.ibatis.plugin.Invocation;
import org.apache.ibatis.plugin.Signature;
import org.apache.ibatis.session.ResultHandler;
import org.apache.ibatis.session.RowBounds;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.support.TransactionTemplate;
import static org.junit.jupiter.api.Assertions.*;

/** 仅根runner的专属MySQL；真实Mapper/源表/本地事务，身份会话为进程内可撤销合成主体。 */
@ActiveProfiles("memory-it")
@EnabledIfSystemProperty(named = "memory.integration.enabled", matches = "true")
@SpringJUnitConfig(MemorySessionBindingIntegrationTest.EmptyConfiguration.class)
class MemorySessionBindingIntegrationTest {
    @Configuration(proxyBeanMethods = false) static class EmptyConfiguration { }

    @Test void actualSourceOwnershipImmutableBindingAndRollback() throws Exception {
        String url = required("MEMORY_IT_MYSQL_JDBC_URL");
        assertTrue(url.startsWith("jdbc:mysql://"), "只接受显式MySQL");
        URI parsed;
        try { parsed = URI.create(url.substring(5)); }
        catch (IllegalArgumentException invalid) { throw new AssertionError("JDBC格式无效"); }
        assertNull(parsed.getUserInfo(), "凭据不得嵌入URL");
        assertTrue(Set.of("127.0.0.1", "localhost", "[::1]", "::1").contains(parsed.getHost()), "仅本机隔离实例");
        String schema = parsed.getPath().substring(1);
        assertTrue(schema.matches("aiep_memory_it_[0-9]{8}_[0-9a-f]{10}"), "禁止非专属库");
        var dataSource = new DriverManagerDataSource(url, required("MEMORY_IT_MYSQL_USER"), required("MEMORY_IT_MYSQL_PASSWORD"));
        try (Connection connection = dataSource.getConnection()) {
            assertEquals("MySQL", connection.getMetaData().getDatabaseProductName());
            try (var statement = connection.createStatement(); var rows = statement.executeQuery("SELECT DATABASE()")) {
                assertTrue(rows.next()); assertEquals(schema, rows.getString(1));
            }
            try (var statement = connection.createStatement(); var rows = statement.executeQuery(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name LIKE 'ai\\_memory\\_%'")) {
                assertTrue(rows.next()); assertEquals(12, rows.getInt(1), "只接受root已审D10 Schema");
            }
            // 沿既有迁移读取两张源表的完整原始CREATE TABLE；不复制DDL、不创建第二份真相。
            createSourceTable(connection, "V1.0.0__operation_assistant_mvp.sql", "ai_operation_conversation");
            createSourceTable(connection, "V1.1.0__customer_service_knowledge_aihub.sql", "ai_customer_service_conversation");
            String first = UUID.randomUUID().toString(), second = UUID.randomUUID().toString();
            insertSource(connection, "ai_operation_conversation", first, "t", "u", "customer-service 假标题");
            insertSource(connection, "ai_customer_service_conversation", first, "t", "u", "operations 假标题");
            insertSource(connection, "ai_operation_conversation", second, "t", "u", "旧运营会话");

            var factory = new MybatisSqlSessionFactoryBean();
            factory.setDataSource(dataSource);
            factory.setMapperLocations(new ClassPathResource("mapper/memory/MemoryMapper.xml"));
            var configuration = new com.baomidou.mybatisplus.core.MybatisConfiguration();
            configuration.setMapUnderscoreToCamelCase(true);
            var gate = new FirstBindingGate();
            configuration.addInterceptor(gate);
            factory.setConfiguration(configuration);
            MemoryMapper mapper = new SqlSessionTemplate(factory.getObject()).getMapper(MemoryMapper.class);
            var transaction = new TransactionTemplate(new DataSourceTransactionManager(dataSource));
            var live = new AtomicBoolean(true);
            IdentityFacade.Subject actor = subject("t", "u");
            IdentityFacade identity = new IdentityFacade() {
                public Optional<Subject> authenticate(String credential) { return Optional.empty(); }
                public Optional<Subject> refresh(String tenant, String user, String ref) {
                    return live.get() && "original".equals(ref) ? Optional.of(subject(tenant, user)) : Optional.empty();
                }
            };
            MemoryActorProvider provider = new MemoryActorProvider() {
                public OperationActor current() { return new OperationActor("t", "u", "original"); }
                public OperationActor revalidate(OperationActor captured) { return captured; }
            };
            var service = new MemorySessionBindingService(mapper, new MemoryScopePolicy(identity, provider), new ConversationScopeResolver());
            var bound = transaction.execute(status -> service.bind(actor, "operations", first));
            assertEquals("operations", bound.topLevelAgentId());
            var stored = transaction.execute(status -> mapper.findSessionBinding(bytes("t"), bytes("u"), bytes(first)));
            assertEquals("OPERATION_CONVERSATION", stored.originalObjectType());
            assertArrayEquals(bytes(first), stored.originalObjectId());
            assertThrows(org.springframework.dao.DuplicateKeyException.class, () -> transaction.execute(status -> mapper.insertSessionBinding(
                    new MemoryMapper.SessionBindingPO(bytes("t"), bytes(UUID.randomUUID().toString()), bytes("u"), "customer-service", "customer-service",
                            bytes(first), "CONVERSATION", "CUSTOMER_SERVICE_CONVERSATION", bytes(first)))));
            assertEquals(bound, transaction.execute(status -> service.bind(actor, "operations", first)));
            assertCode("MEMORY_SESSION_BINDING_CONFLICT", () -> transaction.execute(status -> service.bind(actor, "customer-service", first)));
            assertCode("MEMORY_SCOPE_DENIED", () -> transaction.execute(status -> service.bind(subject("t", "u "), "operations", first)));
            assertCode("MEMORY_SCOPE_DENIED", () -> transaction.execute(status -> service.bind(subject("T", "u"), "operations", first)));
            assertCode("MEMORY_SCOPE_DENIED", () -> transaction.execute(status -> service.bind(subject("t", "other"), "operations", first)));

            transaction.executeWithoutResult(status -> {
                service.bind(actor, "operations", second);
                status.setRollbackOnly();
            });
            assertNull(transaction.execute(status -> mapper.findSessionBinding(bytes("t"), bytes("u"), bytes(second))));
            assertNotNull(transaction.execute(status -> service.bind(actor, "operations", second)));
            try (PreparedStatement statement = connection.prepareStatement("UPDATE ai_operation_conversation SET status='DELETED' WHERE id=?")) {
                statement.setString(1, first); assertEquals(1, statement.executeUpdate());
            }
            assertCode("MEMORY_SCOPE_DENIED", () -> transaction.execute(status -> service.bind(actor, "operations", first)));
            live.set(false);
            assertCode("MEMORY_IDENTITY_REQUIRED", () -> transaction.execute(status -> service.bind(actor, "operations", second)));
            assertEquals("operations", transaction.execute(status -> mapper.findSessionBinding(bytes("t"), bytes("u"), bytes(first))).domain());
            live.set(true);
            concurrentFirstBinding(connection, dataSource, service, mapper, actor, gate, false);
            concurrentFirstBinding(connection, dataSource, service, mapper, actor, gate, true);
        }
    }

    private static void concurrentFirstBinding(Connection connection, DriverManagerDataSource dataSource,
            MemorySessionBindingService service, MemoryMapper mapper, IdentityFacade.Subject actor, FirstBindingGate gate,
            boolean crossAgent) throws Exception {
        String session = UUID.randomUUID().toString();
        insertSource(connection, "ai_operation_conversation", session, "t", "u", "并发运营旧会话");
        if (crossAgent) insertSource(connection, "ai_customer_service_conversation", session, "t", "u", "并发客服旧会话");
        var agents = List.of("operations", crossAgent ? "customer-service" : "operations");
        var ready = new CyclicBarrier(2);
        gate.arm();
        var pool = Executors.newFixedThreadPool(2);
        var results = new ArrayList<ConcurrentResult>();
        try {
            var futures = new ArrayList<java.util.concurrent.Future<ConcurrentResult>>();
            for (String agent : agents) {
                futures.add(pool.submit(() -> {
                    var tx = new TransactionTemplate(new DataSourceTransactionManager(dataSource));
                    var connectionId = new long[1];
                    try {
                        var scope = tx.execute(status -> {
                            try (var statement = DataSourceUtils.getConnection(dataSource).createStatement();
                                    var rows = statement.executeQuery("SELECT CONNECTION_ID()")) {
                                assertTrue(rows.next()); connectionId[0] = rows.getLong(1);
                                ready.await(15, TimeUnit.SECONDS);
                            } catch (Exception failure) { throw new IllegalStateException("并发同步失败", failure); }
                            return service.bind(actor, agent, session);
                        });
                        return new ConcurrentResult(agent, connectionId[0], scope, null);
                    } catch (RuntimeException failure) {
                        return new ConcurrentResult(agent, connectionId[0], null, failure);
                    }
                }));
            }
            for (var future : futures) results.add(future.get(30, TimeUnit.SECONDS));
        } finally {
            gate.disarm();
            pool.shutdownNow();
            assertTrue(pool.awaitTermination(15, TimeUnit.SECONDS));
        }
        assertEquals(2, new HashSet<>(results.stream().map(ConcurrentResult::connectionId).toList()).size(), "必须是两个实际连接");
        assertTrue(results.stream().allMatch(result -> result.connectionId() > 0));
        assertEquals(2, gate.emptyReads(), "双方都在真实FOR UPDATE中看到尚无binding后再竞争插入");
        assertTrue(results.stream().anyMatch(result -> result.scope() != null), "至少一个事务提交真实绑定");
        var tx = new TransactionTemplate(new DataSourceTransactionManager(dataSource));
        var stored = tx.execute(status -> mapper.findSessionBinding(bytes("t"), bytes("u"), bytes(session)));
        assertNotNull(stored);
        String winner = stored.topLevelAgentId();
        for (var result : results) {
            if (result.failure() != null) {
                assertTrue(isDeadlock(result.failure()), "只允许数据库1213死锁保守回滚，不能吞掉其他失败");
            }
            if (!crossAgent || winner.equals(result.agent())) {
                // 竞争结束后仅一次原tuple重入；不在生产服务内重试、不改变身份或Agent。
                var replay = tx.execute(status -> service.bind(actor, result.agent(), session));
                assertEquals(result.agent(), replay.topLevelAgentId());
                if (result.scope() != null) assertEquals(result.scope(), replay);
            } else {
                assertNull(result.scope(), "另一Agent不得报告成功");
                assertCode("MEMORY_SESSION_BINDING_CONFLICT", () -> tx.execute(status -> service.bind(actor, result.agent(), session)));
            }
        }
        var unchanged = tx.execute(status -> mapper.findSessionBinding(bytes("t"), bytes("u"), bytes(session)));
        assertArrayEquals(stored.id(), unchanged.id());
        assertEquals(winner, unchanged.domain());
        assertEquals(winner, unchanged.topLevelAgentId());
        assertEquals("operations".equals(winner) ? "OPERATION_CONVERSATION" : "CUSTOMER_SERVICE_CONVERSATION", unchanged.originalObjectType());
        assertArrayEquals(bytes("t"), unchanged.tenantId());
        assertArrayEquals(bytes("u"), unchanged.userId());
        assertArrayEquals(bytes(session), unchanged.sessionId());
        assertArrayEquals(bytes(session), unchanged.originalObjectId());
        try (var statement = connection.prepareStatement("SELECT COUNT(*) FROM ai_memory_session_binding WHERE tenant_id=? AND user_id=? AND session_id=?")) {
            statement.setBytes(1, bytes("t")); statement.setBytes(2, bytes("u")); statement.setBytes(3, bytes(session));
            try (var rows = statement.executeQuery()) { assertTrue(rows.next()); assertEquals(1, rows.getInt(1)); }
        }
        System.out.println("D11 concurrent binding: crossAgent=" + crossAgent + ", connections=2, missingReads=2, bindings=1, deadlocks="
                + results.stream().filter(result -> result.failure() != null).count());
    }

    private record ConcurrentResult(String agent, long connectionId,
            com.aiep.aihub.api.memory.MemoryScopeDTO scope, RuntimeException failure) { }

    private static boolean isDeadlock(Throwable failure) {
        for (Throwable cause = failure; cause != null; cause = cause.getCause())
            if (cause instanceof SQLException sql && sql.getErrorCode() == 1213 && "40001".equals(sql.getSQLState())) return true;
        return false;
    }

    /** 仅同步真实查询的返回时机，绝不改写SQL、锁或查询结果。 */
    @Intercepts(@Signature(type = Executor.class, method = "query", args = {MappedStatement.class, Object.class, RowBounds.class, ResultHandler.class}))
    public static final class FirstBindingGate implements Interceptor {
        private final AtomicInteger reads = new AtomicInteger();
        private volatile CyclicBarrier barrier;
        void arm() { reads.set(0); barrier = new CyclicBarrier(2); }
        void disarm() { barrier = null; }
        int emptyReads() { return reads.get(); }
        public Object intercept(Invocation invocation) throws Throwable {
            Object result = invocation.proceed();
            var current = barrier;
            if (current != null && ((MappedStatement) invocation.getArgs()[0]).getId().equals(MemoryMapper.class.getName() + ".findSessionBinding")
                    && result instanceof List<?> rows && rows.isEmpty() && reads.incrementAndGet() <= 2)
                current.await(15, TimeUnit.SECONDS);
            return result;
        }
    }

    private static void createSourceTable(Connection connection, String migration, String table) throws Exception {
        Path root = Path.of("").toAbsolutePath();
        while (root != null && !Files.isDirectory(root.resolve("sql/migration"))) root = root.getParent();
        assertNotNull(root, "找不到Java SQL唯一目录");
        String sql = Files.readString(root.resolve("sql/migration").resolve(migration));
        int start = sql.indexOf("CREATE TABLE " + table + " (");
        assertTrue(start >= 0);
        int end = sql.indexOf(';', start);
        assertTrue(end > start);
        try (var statement = connection.createStatement()) { statement.execute(sql.substring(start, end)); }
    }

    private static void insertSource(Connection connection, String table, String id, String tenant, String user, String title) throws Exception {
        // table仅由本测试固定目录传入，不来自业务输入。
        assertTrue(Set.of("ai_operation_conversation", "ai_customer_service_conversation").contains(table));
        try (var statement = connection.prepareStatement("INSERT INTO " + table
                + "(id,tenant_id,user_id,title,status,created_at,updated_at) VALUES(?,?,?,?,'ACTIVE',UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))")) {
            statement.setString(1, id); statement.setString(2, tenant); statement.setString(3, user); statement.setString(4, title);
            assertEquals(1, statement.executeUpdate());
        }
    }
    private static IdentityFacade.Subject subject(String tenant, String user) {
        return new IdentityFacade.Subject(tenant, user, Set.of(), Set.of(), Set.of(), Set.of(), List.of(), "original");
    }
    private static byte[] bytes(String value) { return MemoryMapper.identity(value); }
    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) throw new AssertionError("缺少受控隔离参数");
        return value;
    }
    private static void assertCode(String code, org.junit.jupiter.api.function.Executable action) {
        assertEquals(code, assertThrows(MemoryException.class, action).code());
    }
}

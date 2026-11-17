package com.aiep.aihub.memory;

import com.aiep.platformai.agent.AgentClientProperties;
import com.aiep.platformai.agent.HttpAgentClient;
import com.aiep.platformai.api.dto.MemoryContextEnvelope;
import com.aiep.platformai.api.dto.OperationAgentMessageRequest;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.web.reactive.function.client.WebClient;
import static org.junit.jupiter.api.Assertions.*;

/** 生产Java传输→真实Python HTTP→专属MySQL；不代表Java业务Controller或登录链全栈验收。 */
@ActiveProfiles("memory-it")
@EnabledIfSystemProperty(named = "memory.integration.enabled", matches = "true")
@SpringBootTest(classes = ContextPipelineIntegrationTest.TransportConfiguration.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "spring.config.location=classpath:/application-memory-it.yml")
class ContextPipelineIntegrationTest {
    @Autowired private HttpAgentClient client;
    @Autowired private ObjectMapper json;
    @Autowired private Environment environment;

    @Test
    void realPythonHttpPersistsSixteenAuthorizedSendsForEightJavaScopes() throws Exception {
        String baseUrl = required("MEMORY_IT_AGENT_BASE_URL");
        String jdbcUrl = required("MEMORY_IT_MYSQL_JDBC_URL");
        String secret = required("MEMORY_IT_INTERNAL_SECRET");
        assertTrue(secret.length() >= 32 && !secret.isBlank(), "显式内部认证配置必须有效");
        URI endpoint;
        URI database;
        try {
            endpoint = URI.create(baseUrl);
            assertTrue(jdbcUrl.startsWith("jdbc:mysql://"), "仅接受显式MySQL JDBC连接");
            database = URI.create(jdbcUrl.substring(5));
        } catch (IllegalArgumentException invalid) {
            throw new AssertionError("集成端点格式无效，配置值不输出");
        }
        assertEquals("http", endpoint.getScheme(), "只连接本机Python fixture");
        assertTrue(Set.of("127.0.0.1", "localhost", "[::1]", "::1").contains(endpoint.getHost()), "禁止非本机Agent地址");
        assertNull(endpoint.getUserInfo(), "HTTP地址不得嵌入凭据");
        assertNull(database.getUserInfo(), "JDBC地址不得嵌入凭据");
        String schema = database.getPath().substring(1);
        assertTrue(schema.matches("aiep_memory_it_[0-9]{8}_[0-9a-f]{10}"), "只接受本次专属合成库");
        String user = required("MEMORY_IT_MYSQL_USER");
        String password = required("MEMORY_IT_MYSQL_PASSWORD");
        try (Connection connection = DriverManager.getConnection(jdbcUrl, user, password)) {
            connection.setReadOnly(true);
            assertEquals("MySQL", connection.getMetaData().getDatabaseProductName());
            try (ResultSet result = connection.createStatement().executeQuery("SELECT DATABASE()")) {
                assertTrue(result.next());
                assertEquals(schema, result.getString(1), "实际连接必须是专属库");
            }
            assertEquals(0, count(connection, "agent_context_manifest"), "Java fixture须使用独立空上下文库");
            assertEquals(0, count(connection, "agent_context_operation"));
            assertEquals(0, count(connection, "agent_context_stage"));
            Map<String, MemoryContextEnvelope.Scope> expected = new HashMap<>();
            String prefix = "java-it-" + UUID.randomUUID().toString().substring(0, 8);
            for (String tenant : List.of("synthetic-t1", "synthetic-t2")) {
                for (String subject : List.of("synthetic-u1", "synthetic-u2")) {
                    for (int index = 1; index <= 2; index++) {
                        String session = prefix + "-" + subject + "-" + index;
                        var scope = new MemoryContextEnvelope.Scope(tenant, subject, "operations", "operations", "CONVERSATION", session);
                        var envelope = new MemoryContextEnvelope("memory-context/1", "DISABLED", scope, null);
                        var response = client.submitOperationMessage(session,
                                new OperationAgentMessageRequest("解释品牌定位", prefix + "-" + UUID.randomUUID(), subject, List.of(), tenant, envelope));
                        assertNotNull(response.runId());
                        assertFalse(response.runId().isBlank());
                        assertEquals(session, response.conversationId());
                        assertNull(expected.put(response.runId(), scope), "不同scope须有不同执行引用");
                    }
                }
            }
            assertEquals(8, expected.size());
            long deadline = System.nanoTime() + Duration.ofSeconds(45).toNanos();
            List<JsonNode> manifests = List.of();
            while (System.nanoTime() < deadline) {
                manifests = manifests(connection);
                if (manifests.size() == 16 && succeeded(connection, "agent_context_operation") == 16
                        && succeeded(connection, "agent_context_stage") == 16) break;
                Thread.sleep(100);
            }
            assertEquals(16, manifests.size(), "真实最终发送必须持久化16份Manifest");
            assertEquals(16, count(connection, "agent_context_operation"));
            assertEquals(16, succeeded(connection, "agent_context_operation"));
            assertEquals(16, count(connection, "agent_context_stage"));
            assertEquals(16, succeeded(connection, "agent_context_stage"));
            Map<String, Set<String>> observedNodes = new HashMap<>();
            for (JsonNode manifest : manifests) {
                JsonNode execution = manifest.path("scope");
                String runId = execution.path("execution_id").asText();
                var scope = expected.get(runId);
                assertNotNull(scope, "不得混入其他执行的Manifest");
                assertEquals(json.valueToTree(scope), execution.path("conversation"));
                assertTrue(manifest.at("/measurement/total_upper_bound").asLong() > 0, "真实最终请求上界必须大于零");
                assertEquals("ALLOW", manifest.at("/decision/status").asText());
                assertEquals(1, manifest.path("attempt").asInt());
                assertFalse(manifest.toString().contains("解释品牌定位"), "上下文元数据不得持久化正文");
                observedNodes.computeIfAbsent(runId, ignored -> new HashSet<>()).add(manifest.path("node_id").asText());
            }
            assertEquals(expected.keySet(), observedNodes.keySet());
            observedNodes.values().forEach(nodes -> assertEquals(Set.of("intent", "direct"), nodes));
        }
    }

    private String required(String key) {
        String value = environment.getProperty(key);
        assertTrue(value != null && !value.isBlank(), key + "必须显式提供；不回退共享配置");
        return value;
    }

    private long count(Connection connection, String table) throws Exception {
        try (PreparedStatement statement = connection.prepareStatement("SELECT COUNT(*) FROM " + table);
                ResultSet result = statement.executeQuery()) {
            assertTrue(result.next());
            return result.getLong(1);
        }
    }

    private long succeeded(Connection connection, String table) throws Exception {
        try (PreparedStatement statement = connection.prepareStatement("SELECT COUNT(*) FROM " + table + " WHERE status='SUCCEEDED'");
                ResultSet result = statement.executeQuery()) {
            assertTrue(result.next());
            return result.getLong(1);
        }
    }

    private List<JsonNode> manifests(Connection connection) throws Exception {
        List<JsonNode> result = new ArrayList<>();
        try (PreparedStatement statement = connection.prepareStatement("SELECT metadata_json FROM agent_context_manifest");
                ResultSet rows = statement.executeQuery()) {
            while (rows.next()) result.add(json.readTree(rows.getString(1)));
        }
        return result;
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(AgentClientProperties.class)
    static class TransportConfiguration {
        @Bean ObjectMapper objectMapper() { return new ObjectMapper().findAndRegisterModules(); }
        @Bean HttpAgentClient agentClient(AgentClientProperties properties, ObjectMapper mapper) {
            return new HttpAgentClient(properties, WebClient.builder(), mapper);
        }
    }
}

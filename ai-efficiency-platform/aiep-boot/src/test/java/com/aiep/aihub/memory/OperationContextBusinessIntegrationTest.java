package com.aiep.aihub.memory;

import com.aiep.aihub.application.operation.OperationActor;
import com.aiep.aihub.application.operation.OperationAssistantService;
import com.aiep.aihub.web.memory.MemoryActorResolver;
import com.aiep.aihub.web.operation.OperationAssistantController;
import com.aiep.aihub.web.operation.OperationAssistantExceptionHandler;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.identity.facade.DatabaseIdentityFacade;
import com.aiep.platformai.agent.AgentClientProperties;
import com.aiep.platformai.agent.HttpAgentClient;
import com.aiep.platformai.agent.HttpCustomerServiceAgentClient;
import com.aiep.platformai.facade.AiInvokeFacadeImpl;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.mybatis.spring.annotation.MapperScan;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import static org.junit.jupiter.api.Assertions.*;

/** 真实身份/MyBatis/业务HTTP→AiInvokeFacade→Python，仅供应商Provider为Fake。 */
@ActiveProfiles("memory-it")
@EnabledIfSystemProperty(named = "memory.integration.enabled", matches = "true")
@SpringBootTest(classes = OperationContextBusinessIntegrationTest.BusinessConfiguration.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = {
        "spring.config.location=classpath:/application-memory-it.yml",
        "spring.main.web-application-type=servlet", "server.address=127.0.0.1",
        "spring.datasource.url=${MEMORY_IT_MYSQL_JDBC_URL}",
        "spring.datasource.username=${MEMORY_IT_MYSQL_USER}",
        "spring.datasource.password=${MEMORY_IT_MYSQL_PASSWORD}",
        "mybatis-plus.mapper-locations=classpath*:mapper/identity/*.xml",
        "mybatis-plus.configuration.map-underscore-to-camel-case=true"})
class OperationContextBusinessIntegrationTest {
    @LocalServerPort private int port;
    @Autowired private JdbcTemplate jdbc;
    @Autowired private ObjectMapper json;
    @Autowired private IdentityFacade identity;
    @Autowired private MemoryActorResolver actors;
    @Autowired private AgentClientProperties agentProperties;
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration(excludeName = {"org.redisson.spring.starter.RedissonAutoConfigurationV2",
            "org.springframework.boot.autoconfigure.data.redis.RedisAutoConfiguration",
            "org.springframework.boot.autoconfigure.data.redis.RedisRepositoriesAutoConfiguration"})
    @EnableConfigurationProperties(AgentClientProperties.class)
    @MapperScan({"com.aiep.aihub.repository.operation", "com.aiep.identity.repository"})
    @Import({OperationAssistantService.class, OperationAssistantController.class, OperationAssistantExceptionHandler.class,
            MemoryActorResolver.class, DatabaseIdentityFacade.class, HttpAgentClient.class,
            HttpCustomerServiceAgentClient.class, AiInvokeFacadeImpl.class})
    static class BusinessConfiguration { }

    @Test
    void realIdentityAndBusinessDatabasePreserveEightScopesAndExactLoginRevocation() throws Exception {
        URI fixtureEndpoint = requireLoopbackFixture(agentProperties.getBaseUrl());
        String nonce = System.getenv("MEMORY_IT_FIXTURE_NONCE");
        assertTrue(nonce != null && nonce.matches("[0-9a-f]{32}"), "本次合成fixture证明必须显式提供");
        assertTrue(agentProperties.getInternalSecret() != null && agentProperties.getInternalSecret().length() >= 32);
        JsonNode proof = fixtureProof(fixtureEndpoint);
        assertEquals("FIXED_FAKE", proof.path("provider_mode").asText());
        assertTrue(nonce.equals(proof.path("fixture_nonce").asText()), "目标必须是本次持有的Fake fixture");
        assertEquals(0, proof.path("requests").size());
        String schema = jdbc.queryForObject("SELECT DATABASE()", String.class);
        assertNotNull(schema);
        assertTrue(schema.matches("aiep_memory_it_[0-9]{8}_[0-9a-f]{10}"), "专属合成库是执行DDL前提");
        Path project = Path.of(System.getProperty("user.dir")).toAbsolutePath();
        while (project != null && !Files.isDirectory(project.resolve("sql/migration"))) project = project.getParent();
        assertNotNull(project);
        for (String file : List.of("V1.0.0__operation_assistant_mvp.sql", "V1.0.1__operation_assistant_artifact_versions.sql", "V1.0.2__operation_artifact_platform_versions.sql")) {
            String source = Files.readString(project.resolve("sql/migration").resolve(file)).replaceAll("(?m)--[^\\r\\n]*", "");
            for (String statement : source.split(";")) if (!statement.isBlank()) jdbc.execute(statement);
        }
        String identityDdl = Files.readString(project.resolve("sql/migration/V1.2.3__hr_execution_identity_and_sources.sql"));
        for (String statement : identityDdl.replaceAll("(?m)--[^\\r\\n]*", "").split(";")) {
            if (statement.stripLeading().startsWith("CREATE TABLE id_hr_session ") || statement.stripLeading().startsWith("CREATE TABLE id_hr_grant ")) jdbc.execute(statement);
        }
        assertEquals(401, request("POST", "/api/operations/conversations", null, Map.of("title", "合成会话")).statusCode());
        var credentials = new ArrayList<String>();
        var conversations = new ArrayList<String>();
        var javaRuns = new ArrayList<String>();
        String firstSessionRef = null;
        for (String tenant : List.of("synthetic-t1", "synthetic-t2")) {
            for (String user : List.of("synthetic-u1", "synthetic-u2")) {
                String credential = newCredential();
                seedSession(credential, tenant, user);
                credentials.add(credential);
                var subject = identity.authenticate(credential).orElseThrow();
                assertEquals(tenant, subject.tenantId());
                assertEquals(user, subject.userId());
                if (firstSessionRef == null) firstSessionRef = subject.sessionRef();
                for (int index = 1; index <= 2; index++) {
                    var created = request("POST", "/api/operations/conversations", credential, Map.of("title", "合成会话"));
                    assertEquals(200, created.statusCode());
                    String conversation = json.readTree(created.body()).at("/data/conversationId").asText();
                    assertFalse(conversation.isBlank());
                    conversations.add(conversation);
                    var submitted = request("POST", "/api/operations/conversations/" + conversation + "/messages", credential,
                            Map.of("message", "解释品牌定位", "clientRequestId", "business-it-" + UUID.randomUUID()));
                    assertEquals(202, submitted.statusCode());
                    JsonNode view = json.readTree(submitted.body()).path("data");
                    String javaRun = view.path("runId").asText();
                    String agentRun = view.path("agentRunId").asText();
                    assertFalse(agentRun.isBlank());
                    assertNotEquals(javaRun, agentRun, "业务run与执行run不得混同");
                    javaRuns.add(javaRun);
                    var events = request("GET", "/api/operations/runs/" + javaRun + "/events", credential, null);
                    assertEquals(200, events.statusCode());
                    var completed = request("GET", "/api/operations/runs/" + javaRun, credential, null);
                    assertEquals("succeeded", json.readTree(completed.body()).at("/data/status").asText());
                    List<String> manifests = jdbc.queryForList("SELECT metadata_json FROM agent_context_manifest WHERE tenant_id=? AND execution_id=?", String.class,
                            tenant.getBytes(StandardCharsets.UTF_8), agentRun.getBytes(StandardCharsets.UTF_8));
                    assertEquals(2, manifests.size());
                    JsonNode sends = fixtureProof(fixtureEndpoint).path("requests");
                    for (String payload : manifests) {
                        JsonNode manifest = json.readTree(payload);
                        assertEquals(tenant, manifest.at("/scope/conversation/tenant_id").asText());
                        assertEquals(user, manifest.at("/scope/conversation/user_id").asText());
                        assertEquals(conversation, manifest.at("/scope/conversation/session_id").asText());
                        long upperBound = manifest.at("/measurement/total_upper_bound").asLong();
                        assertTrue(upperBound > 0 && upperBound <= 120000);
                        assertTrue(manifest.at("/measurement/verified").asBoolean());
                        assertEquals("ALLOW", manifest.at("/decision/status").asText());
                        assertEquals(120000, manifest.at("/decision/H_ctx").asLong());
                        assertEquals(upperBound, manifest.at("/decision/T").asLong());
                        assertTrue(manifest.at("/decision/F").asLong() <= upperBound);
                        assertEquals(10000, manifest.path("safety_margin_tokens").asLong());
                        assertTrue(List.of(2000L, 4000L).contains(manifest.path("output_reserve_tokens").asLong()));
                        int matches = 0;
                        for (JsonNode send : sends) {
                            if (agentRun.equals(send.path("execution_id").asText()) && manifest.path("node_id").asText().equals(send.path("node_id").asText())) {
                                matches++;
                                assertEquals(upperBound, send.path("input_upper_bound").asLong(), "清单必须等于Fake边界实收完整请求的独立上界");
                                assertEquals(0, send.path("tool_count").asInt(), "本运营Direct链实际工具数为0");
                            }
                        }
                        assertEquals(1, matches);
                    }
                }
            }
        }
        assertEquals(8, jdbc.queryForObject("SELECT COUNT(*) FROM ai_operation_conversation", Integer.class));
        assertEquals(8, jdbc.queryForObject("SELECT COUNT(*) FROM ai_operation_run WHERE status='succeeded'", Integer.class));
        assertEquals(16, jdbc.queryForObject("SELECT COUNT(*) FROM agent_context_manifest", Integer.class));
        assertEquals(16, jdbc.queryForObject("SELECT COUNT(*) FROM agent_context_operation WHERE status='SUCCEEDED'", Integer.class));
        for (String other : List.of(credentials.get(1), credentials.get(2))) {
            assertEquals(404, request("GET", "/api/operations/conversations/" + conversations.get(0), other, null).statusCode());
            assertEquals(404, request("GET", "/api/operations/runs/" + javaRuns.get(0), other, null).statusCode());
        }
        String secondLogin = newCredential();
        seedSession(secondLogin, "synthetic-t1", "synthetic-u1");
        jdbc.update("UPDATE id_hr_session SET revoked_at=NOW(6) WHERE credential_hash=?", firstSessionRef);
        assertEquals(401, request("GET", "/api/operations/conversations/" + conversations.get(0), credentials.get(0), null).statusCode());
        assertEquals(200, request("GET", "/api/operations/conversations/" + conversations.get(0), secondLogin, null).statusCode());
        String revoked = firstSessionRef;
        assertThrows(org.springframework.web.server.ResponseStatusException.class,
                () -> actors.revalidate(new OperationActor("synthetic-t1", "synthetic-u1", revoked)));
    }

    private HttpResponse<String> request(String method, String path, String credential, Object body) throws Exception {
        var builder = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + path)).timeout(Duration.ofSeconds(30));
        if (credential != null) builder.header("Authorization", "Bearer " + credential);
        if (body != null) builder.header("Content-Type", "application/json");
        builder.method(method, body == null ? HttpRequest.BodyPublishers.noBody() : HttpRequest.BodyPublishers.ofString(json.writeValueAsString(body)));
        return http.send(builder.build(), HttpResponse.BodyHandlers.ofString());
    }

    static URI requireLoopbackFixture(String value) {
        try {
            URI endpoint = URI.create(value);
            if (!"http".equals(endpoint.getScheme()) || !List.of("127.0.0.1", "localhost", "[::1]", "::1").contains(endpoint.getHost())
                    || endpoint.getPort() <= 0 || endpoint.getUserInfo() != null || endpoint.getQuery() != null || endpoint.getFragment() != null
                    || !(endpoint.getPath() == null || endpoint.getPath().isEmpty() || "/".equals(endpoint.getPath()))) {
                throw new IllegalArgumentException();
            }
            return endpoint;
        } catch (RuntimeException invalid) { throw new IllegalArgumentException("MEMORY_IT_LOOPBACK_REQUIRED"); }
    }

    private JsonNode fixtureProof(URI endpoint) throws Exception {
        var proof = http.send(HttpRequest.newBuilder(endpoint.resolve("/__memory_it__/proof")).timeout(Duration.ofSeconds(5))
                .header("Authorization", "Bearer " + agentProperties.getInternalSecret()).build(), HttpResponse.BodyHandlers.ofString());
        assertEquals(200, proof.statusCode(), "合成fixture必须在派发前可验证");
        return json.readTree(proof.body());
    }

    private String newCredential() { return UUID.randomUUID().toString().replace("-", "") + UUID.randomUUID().toString().replace("-", ""); }

    private void seedSession(String credential, String tenant, String user) throws Exception {
        String hash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(credential.getBytes(StandardCharsets.UTF_8)));
        jdbc.update("INSERT INTO id_hr_session (credential_hash,tenant_id,user_id,expires_at) VALUES (?,?,?,?)", hash, tenant, user, java.sql.Timestamp.from(Instant.now().plusSeconds(600)));
    }
}

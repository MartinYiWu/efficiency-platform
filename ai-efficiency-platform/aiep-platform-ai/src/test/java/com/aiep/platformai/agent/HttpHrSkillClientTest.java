package com.aiep.platformai.agent;

import static org.junit.jupiter.api.Assertions.*;
import com.aiep.platformai.api.dto.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;

class HttpHrSkillClientTest {
    @Test void hr_has_independent_timeout_authenticated_tenant_and_bounded_large_response() throws Exception {
        HttpServer server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        String secret="synthetic-internal-secret-0000000000000";String content="x".repeat(300_000);
        var json=new ObjectMapper();
        server.createContext("/skill/execute",exchange->{
            try {
                assertEquals("Bearer "+secret,exchange.getRequestHeaders().getFirst("Authorization"));
                assertEquals("t",exchange.getRequestHeaders().getFirst("X-Tenant-ID"));
                String body=new String(exchange.getRequestBody().readAllBytes(),StandardCharsets.UTF_8);assertFalse(body.contains("tenantId"));assertFalse(body.contains(secret));
                try{Thread.sleep(100);}catch(InterruptedException interrupted){Thread.currentThread().interrupt();}
                byte[] response=json.writeValueAsBytes(new AiTextResponse(content));exchange.getResponseHeaders().set("Content-Type","application/json");exchange.sendResponseHeaders(200,response.length);exchange.getResponseBody().write(response);
            } finally {exchange.close();}
        });server.start();
        try {
            var properties=new AgentClientProperties();properties.setBaseUrl("http://127.0.0.1:"+server.getAddress().getPort());properties.setResponseTimeout(Duration.ofMillis(20));properties.setInternalSecret(secret);
            var client=new HttpAgentClient(properties,WebClient.builder(),json);
            var output=client.executeSkill(new AiSkillExecuteRequest(new AiRequestContext("trace",1L,"HR","HR_SKILL"),6102L,"{}","t"));
            assertEquals(content,output.content());
        } finally {server.stop(0);}
    }
    @Test void hr_is_closed_before_network_without_internal_auth_or_tenant() {
        var client=new HttpAgentClient(new AgentClientProperties(),WebClient.builder(),new ObjectMapper());
        assertThrows(AgentTransportException.class,()->client.executeSkill(new AiSkillExecuteRequest(new AiRequestContext("trace",1L,"HR","HR_SKILL"),6101L,"{}","t")));
    }
}

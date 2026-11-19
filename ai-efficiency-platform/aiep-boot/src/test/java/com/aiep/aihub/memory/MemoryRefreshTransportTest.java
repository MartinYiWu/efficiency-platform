package com.aiep.aihub.memory;

import com.aiep.platformai.agent.*;
import com.aiep.platformai.api.dto.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;
import static org.junit.jupiter.api.Assertions.*;

/** 合成loopback接收端验证实际HTTP，不代表Agent/双库已经接合。 */
class MemoryRefreshTransportTest {
    @Test void waitGetAndConflictReceiptKeepStrictDtosAndInternalHeaders()throws Exception {
        var json=new ObjectMapper();var fixture=json.readTree(Files.readString(Path.of("../../efficiency-platform-agent/tests/fixtures/memory_refresh_transport.json")));
        var wait=fixture.get("wait");var request=json.treeToValue(fixture.get("resume"),MemoryResumeRequest.class);
        var receipt=(com.fasterxml.jackson.databind.node.ObjectNode)fixture.get("receipt").deepCopy();
        receipt.put("code","MEMORY_REFRESH_PACKET_EXPIRED");receipt.put("candidate_phase","EXPIRED_UNAPPLIED");receipt.put("state","WAITING_CONTEXT");
        receipt.put("current_packet_revision",1);receipt.put("current_context_fingerprint",request.expectedCurrentContextFingerprint());receipt.put("dispatch_allowed",false);
        var auth=new AtomicReference<String>();var tenant=new AtomicReference<String>();var body=new AtomicReference<String>();
        var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        server.createContext("/",exchange->{
            try {
                auth.set(exchange.getRequestHeaders().getFirst("Authorization"));tenant.set(exchange.getRequestHeaders().getFirst("X-Tenant-ID"));
                body.set(new String(exchange.getRequestBody().readAllBytes(),StandardCharsets.UTF_8));
                boolean get=exchange.getRequestMethod().equals("GET");byte[] bytes=json.writeValueAsBytes(get?wait:receipt);
                exchange.getResponseHeaders().set("Content-Type","application/json");exchange.sendResponseHeaders(get?200:409,bytes.length);exchange.getResponseBody().write(bytes);
            }finally{exchange.close();}
        });server.start();
        try {
            var props=new AgentClientProperties();props.setBaseUrl("http://127.0.0.1:"+server.getAddress().getPort());props.setInternalSecret("synthetic-refresh-secret-00000000000000000000");
            var client=new HttpAgentClient(props,WebClient.builder(),json);
            assertEquals(json.treeToValue(wait,MemoryContextWait.class),client.queryMemoryWait("synthetic-tenant","execution"));
            assertEquals("",body.get());assertEquals("synthetic-tenant",tenant.get());assertEquals("Bearer "+props.getInternalSecret(),auth.get());
            var result=client.resumeMemoryExecution("synthetic-tenant","execution",request);
            assertEquals(MemoryResumeReceipt.CandidatePhase.EXPIRED_UNAPPLIED,result.candidatePhase());
            assertEquals(fixture.get("resume"),json.readTree(body.get()));assertFalse(body.get().contains(props.getInternalSecret()));
        }finally{server.stop(0);}
    }
}

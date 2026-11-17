package com.aiep.platformai.agent;
import static org.junit.jupiter.api.Assertions.*;
import com.aiep.platformai.api.dto.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.function.client.*;
import reactor.core.publisher.Mono;
class HrErrorCodeTransportTest {
 @Test void safe_budget_ledger_and_price_codes_survive_the_skill_http_boundary(){
  for(var code:new String[]{"WORKLOAD_PLAN_EXHAUSTED","LEDGER_UNAVAILABLE","UNKNOWN_PRICE"}){
   var properties=new AgentClientProperties();properties.setBaseUrl("http://127.0.0.1:1");properties.setInternalSecret("s".repeat(32));var builder=WebClient.builder().exchangeFunction(request->Mono.just(ClientResponse.create(HttpStatus.CONFLICT).header("Content-Type","application/json").body("{\"code\":\""+code+"\"}").build()));var client=new HttpAgentClient(properties,builder,new ObjectMapper());var request=new AiSkillExecuteRequest(new AiRequestContext("trace",1L,"HR","TEST"),6103L,"{}","t");assertEquals(code,assertThrows(AgentTransportException.class,()->client.executeSkill(request)).getErrorCode());
  }
 }
}


package com.aiep.aihub.memory;

import com.aiep.aihub.application.memory.MemoryPolicyService;
import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.repository.memory.MemoryMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

class MemoryArtifactPolicyTest {
    @org.junit.jupiter.api.Test void provisionedBackendIsReadableButNeverProvesNoIndex() throws Exception {
        var json=new com.fasterxml.jackson.databind.ObjectMapper();
        var root=json.readTree("{\"artifacts\":{\"schema_version\":\"memory-artifacts/1\",\"index_mode\":\"PROVISIONED\",\"index_backends\":[\"agent-pg-memory-index/1\"]}}");
        org.junit.jupiter.api.Assertions.assertDoesNotThrow(()->MemoryPolicyService.requireProvisionedIndex(root));
        org.junit.jupiter.api.Assertions.assertThrows(com.aiep.aihub.api.memory.MemoryContracts.MemoryException.class,()->MemoryPolicyService.requireUnprovisionedIndex(root));
        var row=new com.aiep.aihub.repository.memory.MemoryMapper.PolicyPO(new byte[]{1},new byte[]{2},root.toString(),null,"memory-policy/1");
        org.junit.jupiter.api.Assertions.assertDoesNotThrow(()->MemoryPolicyService.requireArtifactPolicy(row));
        ((com.fasterxml.jackson.databind.node.ObjectNode)root.path("artifacts")).putArray("index_backends").add("unknown");
        org.junit.jupiter.api.Assertions.assertThrows(com.aiep.aihub.api.memory.MemoryContracts.MemoryException.class,()->MemoryPolicyService.requireProvisionedIndex(root));
    }
    private static final ObjectMapper JSON=new ObjectMapper();
    static String withArtifacts(String json){
        try{
            var root=(ObjectNode)JSON.readTree(json);
            root.set("artifacts",JSON.valueToTree(Map.of("schema_version","memory-artifacts/1","index_mode","NOT_PROVISIONED","index_backends",List.of())));
            return JSON.writeValueAsString(root);
        }catch(Exception failure){throw new IllegalArgumentException(failure);}
    }
    @Test void onlyExplicitEmptyBackendContractIsSupported()throws Exception{
        var root=JSON.readTree(withArtifacts("{}"));
        assertDoesNotThrow(()->MemoryPolicyService.requireUnprovisionedIndex(root));
        for(String bad:List.of("{}","{\"artifacts\":null}","{\"artifacts\":[]}",
            "{\"artifacts\":{\"schema_version\":\"memory-artifacts/1\",\"index_mode\":\"NOT_PROVISIONED\",\"index_backends\":[\"legacy\"]}}",
            "{\"artifacts\":{\"schema_version\":\"memory-artifacts/2\",\"index_mode\":\"NOT_PROVISIONED\",\"index_backends\":[]}}",
            "{\"artifacts\":{\"schema_version\":\"memory-artifacts/1\",\"index_mode\":\"DISABLED\",\"index_backends\":[]}}")){
            var value=JSON.readTree(bad);assertEquals("FEATURE_DISABLED",assertThrows(MemoryException.class,()->MemoryPolicyService.requireUnprovisionedIndex(value)).code());
        }
        ((ObjectNode)root.path("artifacts")).put("unknown",true);
        assertThrows(MemoryException.class,()->MemoryPolicyService.requireUnprovisionedIndex(root));
    }
    @Test void originalVersionCannotBorrowCurrentPolicyProof(){
        var mapper=mock(MemoryMapper.class);var service=new MemoryPolicyService(mapper);
        var requested=List.of(new MemoryMapper.VersionIdentityPO("i".getBytes(),"v".getBytes()));
        var legacy=new MemoryMapper.VersionPolicyPO("i".getBytes(),"v".getBytes(),"p".getBytes(),"old".getBytes(),"{}","memory-policy/1");
        when(mapper.listVersionPolicies(any(),eq(requested))).thenReturn(List.of(legacy));
        assertThrows(MemoryException.class,()->service.requireVersionArtifacts("t".getBytes(),requested));
        verify(mapper,never()).findPublishedPolicy(any(),any());
        var valid=new MemoryMapper.VersionPolicyPO("i".getBytes(),"v".getBytes(),"p".getBytes(),"old".getBytes(),withArtifacts("{}"),"memory-policy/1");
        when(mapper.listVersionPolicies(any(),eq(requested))).thenReturn(List.of(valid));
        assertDoesNotThrow(()->service.requireVersionArtifacts("t".getBytes(),requested));
        when(mapper.listVersionPolicies(any(),eq(requested))).thenReturn(List.of());
        assertThrows(MemoryException.class,()->service.requireVersionArtifacts("t".getBytes(),requested));
        when(mapper.listVersionPolicies(any(),eq(requested))).thenReturn(List.of(valid,valid));
        assertThrows(MemoryException.class,()->service.requireVersionArtifacts("t".getBytes(),requested));
    }
}

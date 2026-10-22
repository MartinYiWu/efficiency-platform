package com.aiep.platformai.api.dto;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class CustomerServiceDebugViewTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void readsParentChildDebugFactsAndOldResponse() throws Exception {
        String response = """
                {"contract_version":"customer-service-rag-debug-view/1","debug_run_id":"run-1",
                 "status":"SUCCEEDED","stages":[],"answer_mode":"COMPANY_KNOWLEDGE",
                 "answer_markdown":"答复","error_code":null,"error_message":null,
                 "child_hits":[{"chunk_id":"child-1","parent_id":"parent-1",
                   "document_version_id":"version-1","index_release_id":"index-1",
                   "score":0.9,"excerpt":"例外"}],
                 "parent_evidence":[{"parent_id":"parent-1","document_version_id":"version-1",
                   "index_release_id":"index-1","document_title":"制度","version_no":2,
                   "section_path":"请假","content":"完整条款","hit_chunk_ids":["child-1"]}],
                 "assembly_decisions":[{"parent_id":"parent-1","selected":true,"reason":"SELECTED"}],
                 "budget_usage":{"context_token_limit":8000,"used_tokens":4500},
                 "sufficiency":null}
                """;
        CustomerServiceDebugView parsed = mapper.readValue(response, CustomerServiceDebugView.class);
        assertEquals("parent-1", parsed.childHits().getFirst().parentId());
        assertEquals("完整条款", parsed.parentEvidence().getFirst().content());
        assertEquals(4500, parsed.budgetUsage().usedTokens());

        String legacy = """
                {"contract_version":"customer-service-rag-debug-view/1","debug_run_id":"run-0",
                 "status":"SUCCEEDED","stages":[],"answer_mode":null,"answer_markdown":null,
                 "error_code":null,"error_message":null}
                """;
        assertNull(mapper.readValue(legacy, CustomerServiceDebugView.class).parentEvidence());
    }

    @Test
    void readsInternalRetrievalFactsFromAgentEvent() throws Exception {
        String event = """
                {"contract_version":"customer-service-run-event/1","run_id":"run-1","sequence":2,
                 "event_type":"stage.completed","status":"RUNNING","occurred_at":"2026-10-22T00:00:00Z",
                 "payload":{"stage":"retrieval","retrieval_facts":{
                   "child_hits":[],"parent_evidence":[],"assembly_decisions":[],
                   "budget_usage":{"context_token_limit":8000,"used_tokens":4500},"sufficiency":null}}}
                """;
        CustomerServiceRunEvent parsed = mapper.findAndRegisterModules()
                .readValue(event, CustomerServiceRunEvent.class);
        assertEquals(4500, parsed.payload().retrievalFacts().budgetUsage().usedTokens());
    }
}

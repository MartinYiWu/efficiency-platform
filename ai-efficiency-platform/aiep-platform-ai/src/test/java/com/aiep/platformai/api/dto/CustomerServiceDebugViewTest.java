package com.aiep.platformai.api.dto;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class CustomerServiceDebugViewTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void preservesFrozenEvidenceFactsAndZeroRanksWithoutInventingLegacyFacts() throws Exception {
        String json = """
                {"child_hits":[{"chunk_id":"child","parent_id":"parent","knowledge_base_id":"kb",
                  "document_id":"doc","document_version_id":"version","index_release_id":"idx",
                  "rank":1,"query_index":1,"score":0.0,"excerpt":"原文"}],
                 "equivalence_decisions":[],"equivalence_errors":[],"version_exclusions":[],
                 "evidence_groups":[{"parent_ids":["p1","p2"]}],"grouping_decisions":[],
                 "final_parent_candidates":["p1"],
                 "conflict_screen":{"pairs":[],"errors":[],"blocked":false},
                 "evidence_pack":{"entries":[],"groups":[],"exclusions":[{"parent_id":"p1","reason":"BUDGET_EXCLUDED"}],
                  "model_policy":null,"budget":{"context_token_limit":8000,"reserved_tokens":100,"used_tokens":0,
                  "output_tokens":10,"safety_tokens":20,"fixed_input_tokens":70,"intermediate_output_tokens":0,"evidence_tokens":0},
                  "blocked":true,"block_reasons":["BUDGET_EXCLUDED"],"extraction_decisions":[],"conflict_screen":null}}
                """;
        var parsed = mapper.readValue(json, CustomerServiceRunEvent.RetrievalFacts.class);
        com.fasterxml.jackson.databind.node.ObjectNode serialized = mapper.valueToTree(parsed);
        for (var field : mapper.readTree(json).properties()) assertEquals(field.getValue(), serialized.get(field.getKey()));
    }

    @Test
    void preservesExtractedCitationOffsetsAndRejectsInvalidType() throws Exception {
        String json = """
                {"citation_no":1,"quoted_text":"原文","parent_id":"parent","citation_type":"EXTRACTED_SPANS",
                 "original_spans":[{"start_offset":0,"end_offset":2,"content_hash":"hash"}]}
                """;
        var parsed = mapper.readValue(json, CustomerServiceRunEvent.Citation.class);
        assertEquals("EXTRACTED_SPANS", mapper.valueToTree(parsed).path("citation_type").asText());
        org.junit.jupiter.api.Assertions.assertThrows(Exception.class, () -> mapper.readValue(
                json.replace("EXTRACTED_SPANS", "SUMMARY"), CustomerServiceRunEvent.Citation.class));
        org.junit.jupiter.api.Assertions.assertThrows(Exception.class, () -> mapper.readValue(
                json.replace("\"end_offset\":2", "\"end_offset\":0"), CustomerServiceRunEvent.Citation.class));
    }

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
    void readsFinalCitationSnapshotsAndKeepsLegacyResponsesCompatible() throws Exception {
        String response = """
                {"contract_version":"customer-service-rag-debug-view/1","debug_run_id":"run-1",
                 "status":"SUCCEEDED","stages":[],"answer_mode":"COMPANY_KNOWLEDGE",
                 "answer_markdown":"答复[1]","error_code":null,"error_message":null,
                 "citations":[{"citation_no":1,"knowledge_base_id":"kb","document_id":"doc",
                   "document_version_id":"version","index_release_id":"index","chunk_id":"chunk",
                   "document_title":"研发规范","version_no":2,"section_path":"安全","page_no":3,
                   "quoted_text":"禁止输入敏感信息","content_hash":"hash","parent_id":"parent",
                   "citation_type":"EXTRACTED_SPANS","original_spans":[{"start_offset":0,
                   "end_offset":8,"content_hash":"span-hash"}]}]}
                """;
        CustomerServiceDebugView parsed = mapper.readValue(response, CustomerServiceDebugView.class);
        assertEquals("研发规范", parsed.citations().getFirst().documentTitle());
        assertEquals("version", parsed.citations().getFirst().documentVersionId());
        assertEquals("EXTRACTED_SPANS", parsed.citations().getFirst().citationType());

        String legacy = """
                {"contract_version":"customer-service-rag-debug-view/1","debug_run_id":"run-0",
                 "status":"SUCCEEDED","stages":[],"answer_mode":null,"answer_markdown":null,
                 "error_code":null,"error_message":null}
                """;
        assertNull(mapper.readValue(legacy, CustomerServiceDebugView.class).citations());
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

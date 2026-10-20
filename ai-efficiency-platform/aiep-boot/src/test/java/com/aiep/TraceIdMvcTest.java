package com.aiep;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.aiep.aihub.application.operation.OperationAssistantService;
import com.aiep.knowledge.application.KnowledgeBaseService;
import com.aiep.knowledge.application.KnowledgeDocumentService;
import com.aiep.knowledge.application.KnowledgeImportService;
import com.aiep.knowledge.application.KnowledgeReleaseService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(classes = BootApplication.class)
@AutoConfigureMockMvc
class TraceIdMvcTest {
    @MockBean
    private OperationAssistantService operationAssistantService;

    @MockBean
    private KnowledgeBaseService knowledgeBaseService;

    @MockBean
    private KnowledgeDocumentService knowledgeDocumentService;

    @MockBean
    private KnowledgeImportService knowledgeImportService;

    @MockBean
    private KnowledgeReleaseService knowledgeReleaseService;

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returns_the_incoming_trace_id_on_platform_requests() throws Exception {
        mockMvc.perform(get("/api/platform/ping").header("X-Trace-Id", "trace-mvc-test"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Trace-Id", "trace-mvc-test"));
    }
}

package com.aiep.aihub.management;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.aiep.aihub.application.management.AiRagDebugService;
import com.aiep.aihub.repository.management.AiManagementMappers;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentDefinitionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionPolicyBindingPO;
import com.aiep.aihub.repository.management.AiManagementPOs.RagPolicyPO;
import com.aiep.aihub.repository.management.AiReleasePO;
import com.aiep.aihub.web.management.AiManagementExceptionHandler;
import com.aiep.aihub.web.management.AiRagDebugController;
import com.aiep.platformai.api.AiInvokeFacade;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.LocalDateTime;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.ResultSetExtractor;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class AiRagDebugControllerTest {
    private static final LocalDateTime NOW = LocalDateTime.of(2026, 10, 27, 12, 0);
    private static final String REQUEST = """
            {"agentKey":"customer-service","question":"发布流程是什么？",
             "agentVersionId":"version-1","ragPolicyVersionId":"rag-1",
             "knowledgeBindings":[{"knowledgeBaseId":"kb-1","indexReleaseId":"index-retired"}]}
            """;
    private final AiManagementMappers repository = mock(AiManagementMappers.class);
    private final AiInvokeFacade ai = mock(AiInvokeFacade.class);
    private final JdbcTemplate jdbc = mock(JdbcTemplate.class);
    private final AiRagDebugService service = new AiRagDebugService(repository, ai, jdbc, new ObjectMapper());
    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        mvc = MockMvcBuilders.standaloneSetup(new AiRagDebugController(service))
                .setControllerAdvice(new AiManagementExceptionHandler()).build();
        when(repository.findAgentByKey("customer-service")).thenReturn(new AgentDefinitionPO(
                "agent-1", "customer-service", "智能客服", null, "CHAT", "ACTIVE", "1", NOW, "1", NOW));
        when(repository.findAgentVersion("version-1")).thenReturn(new AgentVersionPO(
                "version-1", "agent-1", "1.0.0", "customer-service", "1", "RELEASED", null, "1", NOW, NOW));
        when(repository.findRagPolicy("rag-1")).thenReturn(new RagPolicyPO(
                "rag-1", "agent-1", "default", "1.0.0", 1, 20, 20, 20, 10, 8000, 5,
                "PUBLISHED", "checksum", "1", NOW, NOW, 5, null, null, null));
        when(repository.findActiveRelease("agent-1", "dev")).thenReturn(new AiReleasePO(
                "release-1", "agent-1", "version-1", "dev", "ACTIVE", "snapshot-1", "1", NOW, null, NOW));
        when(repository.findPolicyBinding("version-1"))
                .thenReturn(new AgentVersionPolicyBindingPO("version-1", "model-1", "rag-1", null));
    }

    @Test
    void rejectsIndexThatIsNotReleaseReadyWithBusinessCode() throws Exception {
        when(repository.isIndexReleaseReady("index-retired")).thenReturn(false);

        mvc.perform(post("/api/aihub/rag-debug-runs").contentType(MediaType.APPLICATION_JSON).content(REQUEST))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("AI_RAG_DEBUG_INDEX_NOT_READY"))
                .andExpect(jsonPath("$.message").value("调试知识索引未就绪，请选择已发布且可用的索引"));
        verifyNoInteractions(ai, jdbc);
    }

    @ParameterizedTest
    @ValueSource(strings = {"version", "rag"})
    void rejectsAssetsOwnedByAnotherAgentWithBusinessCode(String asset) throws Exception {
        if (asset.equals("version")) {
            when(repository.findAgentVersion("version-1")).thenReturn(new AgentVersionPO(
                    "version-1", "agent-other", "1.0.0", "customer-service", "1", "RELEASED", null, "1", NOW, NOW));
        } else {
            when(repository.findRagPolicy("rag-1")).thenReturn(new RagPolicyPO(
                    "rag-1", "agent-other", "default", "1.0.0", 1, 20, 20, 20, 10, 8000, 5,
                    "PUBLISHED", "checksum", "1", NOW, NOW, 5, null, null, null));
        }

        mvc.perform(post("/api/aihub/rag-debug-runs").contentType(MediaType.APPLICATION_JSON).content(REQUEST))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("AI_ASSET_OWNER_MISMATCH"));
        verifyNoInteractions(ai, jdbc);
    }

    @ParameterizedTest
    @ValueSource(strings = {"missing-release", "version", "policy"})
    void rejectsDebugRequestThatDoesNotMatchActiveReleaseWithBusinessCode(String mismatch) throws Exception {
        if (mismatch.equals("missing-release")) {
            when(repository.findActiveRelease("agent-1", "dev")).thenReturn(null);
        } else if (mismatch.equals("version")) {
            when(repository.findActiveRelease("agent-1", "dev")).thenReturn(new AiReleasePO(
                    "release-1", "agent-1", "version-other", "dev", "ACTIVE", "snapshot-1", "1", NOW, null, NOW));
        } else {
            when(repository.findPolicyBinding("version-1"))
                    .thenReturn(new AgentVersionPolicyBindingPO("version-1", "model-1", "rag-other", null));
        }

        mvc.perform(post("/api/aihub/rag-debug-runs").contentType(MediaType.APPLICATION_JSON).content(REQUEST))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("AI_RAG_DEBUG_ACTIVE_RELEASE_MISMATCH"));
        verifyNoInteractions(ai, jdbc);
    }

    @Test
    void returnsNotFoundForMissingDebugRun() throws Exception {
        mvc.perform(get("/api/aihub/rag-debug-runs/missing-run"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("AI_RAG_DEBUG_RUN_NOT_FOUND"))
                .andExpect(jsonPath("$.message").value("RAG 调试记录不存在"));
        verifyNoInteractions(ai);
    }

    @Test
    void corruptStoredResultRemainsAnInternalFailure() {
        when(jdbc.query(eq("SELECT response_json FROM ai_rag_debug_run WHERE id=?"),
                org.mockito.ArgumentMatchers.<ResultSetExtractor<String>>any(), eq("corrupt-run")))
                .thenReturn("{invalid-json");

        assertThatThrownBy(() -> service.get("corrupt-run"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("AI_RAG_DEBUG_RESULT_INVALID");
    }
}

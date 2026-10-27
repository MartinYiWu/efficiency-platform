package com.aiep.aihub.customer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.ArgumentMatchers.any;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.aiep.aihub.application.customer.CustomerServiceApplicationService;
import com.aiep.aihub.application.customer.CustomerServiceConversationTitles.TitleException;
import com.aiep.aihub.application.customer.CustomerServiceEventProjector;
import com.aiep.aihub.application.customer.CustomerServicePendingRunCreator;
import com.aiep.aihub.repository.customer.JdbcCustomerServiceMappers;
import com.aiep.aihub.repository.management.AiManagementMappers;
import com.aiep.aihub.web.customer.CustomerServiceController;
import com.aiep.aihub.web.customer.CustomerServiceExceptionHandler;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.CustomerServiceRunEvent;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabase;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseBuilder;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.support.TransactionTemplate;

class CustomerServiceConversationTitlesTest {
    private EmbeddedDatabase database;
    private JdbcTemplate jdbc;
    private JdbcCustomerServiceMappers repository;
    private CustomerServiceApplicationService service;
    private CustomerServiceEventProjector projector;
    private final ObjectMapper mapper = new ObjectMapper().findAndRegisterModules();
    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        database = new EmbeddedDatabaseBuilder().setType(EmbeddedDatabaseType.H2)
                .setName(java.util.UUID.randomUUID() + ";MODE=MySQL;DATABASE_TO_LOWER=TRUE").build();
        jdbc = new JdbcTemplate(database) {
            @Override public int update(String sql, Object... args) {
                // H2 不支持现有运行状态 SQL 的 MySQL IF 表达式，保持测试使用相同更新条件。
                return super.update(sql.replace("finished_at=IF(? IN ('SUCCEEDED','FAILED','TIMED_OUT','CANCELLED'),NOW(6),finished_at)",
                        "finished_at=CASE WHEN ? IN ('SUCCEEDED','FAILED','TIMED_OUT','CANCELLED') THEN NOW(6) ELSE finished_at END"), args);
            }
        };
        jdbc.execute("""
                CREATE TABLE ai_customer_service_conversation(id VARCHAR(36) PRIMARY KEY,tenant_id VARCHAR(64),user_id VARCHAR(64),
                title VARCHAR(255),status VARCHAR(32),last_message_at TIMESTAMP,created_at TIMESTAMP,updated_at TIMESTAMP,
                title_unique_key VARCHAR(255) GENERATED ALWAYS AS
                (CASE WHEN status <> 'DELETED' AND TRIM(title) <> '' THEN LOWER(TRIM(title)) ELSE NULL END),
                CONSTRAINT uk_ai_cs_conversation_title UNIQUE(tenant_id,user_id,title_unique_key))
                """);
        jdbc.execute("""
                CREATE TABLE ai_customer_service_message(id VARCHAR(36) PRIMARY KEY,conversation_id VARCHAR(36),tenant_id VARCHAR(64),
                role VARCHAR(32),content_markdown VARCHAR(4000),status VARCHAR(32),answer_mode VARCHAR(64),run_id VARCHAR(36),
                client_request_id VARCHAR(36),created_at TIMESTAMP)
                """);
        jdbc.execute("""
                CREATE TABLE ai_customer_service_run(id VARCHAR(36) PRIMARY KEY,conversation_id VARCHAR(36),tenant_id VARCHAR(64),
                user_message_id VARCHAR(36),agent_run_id VARCHAR(36),agent_release_id VARCHAR(36),status VARCHAR(32),answer_mode VARCHAR(64),
                last_event_sequence BIGINT,failure_code VARCHAR(255),failure_message VARCHAR(255),started_at TIMESTAMP,
                finished_at TIMESTAMP,created_at TIMESTAMP,updated_at TIMESTAMP)
                """);
        jdbc.execute("""
                CREATE TABLE ai_customer_service_run_step(id VARCHAR(36) PRIMARY KEY,run_id VARCHAR(36),sequence_no BIGINT,
                stage VARCHAR(64),status VARCHAR(32),public_summary VARCHAR(255),internal_payload JSON,started_at TIMESTAMP,finished_at TIMESTAMP,
                UNIQUE(run_id,sequence_no))
                """);
        repository = new JdbcCustomerServiceMappers(jdbc);
        service = new CustomerServiceApplicationService(repository, mock(AiManagementMappers.class),
                new CustomerServicePendingRunCreator(repository), mock(AiInvokeFacade.class));
        projector = new CustomerServiceEventProjector(repository, mapper);
        mvc = MockMvcBuilders.standaloneSetup(new CustomerServiceController(service, projector))
                .setControllerAdvice(new CustomerServiceExceptionHandler()).build();
    }

    @AfterEach
    void tearDown() { database.shutdown(); }

    @Test
    void submissionKeepsTitleEmptyUntilIntentEventArrives() {
        var conversation = service.createConversation("dev", "owner", null);
        pending(conversation.id(), "r1");
        assertThat(service.getConversation("dev", "owner", conversation.id()).title()).isEmpty();
    }

    @Test
    void duplicateIncludesArchivedAndAllowsDeletedOtherOwnerAndSameConversation() throws Exception {
        var first = service.createConversation("dev", "1", "  Title  ");
        service.updateConversation("dev", "1", first.id(), null, "ARCHIVED");
        mvc.perform(post("/api/customer-service/conversations").contentType(MediaType.APPLICATION_JSON).content("{\"title\":\"title\"}"))
                .andExpect(status().isConflict()).andExpect(jsonPath("$.code").value("CUSTOMER_SERVICE_CONVERSATION_TITLE_DUPLICATE"))
                .andExpect(jsonPath("$.message").value("会话名称已存在，请使用其他标题"));
        service.createConversation("dev", "other", "title");
        service.createConversation("other", "1", "title");
        service.updateConversation("dev", "1", first.id(), " Title ", null);
        assertThat(service.getConversation("dev", "1", first.id()).title()).isEqualTo("Title");
        service.deleteConversation("dev", "1", first.id());
        assertThat(service.createConversation("dev", "1", "title").title()).isEqualTo("title");
    }

    @Test
    void manualTitleValidationKeepsOriginal() throws Exception {
        var conversation = service.createConversation("dev", "1", "原名");
        mvc.perform(patch("/api/customer-service/conversations/" + conversation.id()).contentType(MediaType.APPLICATION_JSON).content("{\"title\":\"   \"}"))
                .andExpect(status().isBadRequest()).andExpect(jsonPath("$.message").value("会话名称不能为空"));
        mvc.perform(patch("/api/customer-service/conversations/" + conversation.id()).contentType(MediaType.APPLICATION_JSON)
                        .content(mapper.writeValueAsString(java.util.Map.of("title", "长".repeat(81)))))
                .andExpect(status().isBadRequest()).andExpect(jsonPath("$.message").value("会话名称不能超过80个字符"));
        assertThat(service.getConversation("dev", "1", conversation.id()).title()).isEqualTo("原名");
        assertThat(service.createConversation("dev", "1", "").title()).isEmpty();
    }

    @Test
    void autoTitleUsesActualOwnerAndFirstUserWithSuffixAndReplayProtection() throws Exception {
        service.createConversation("dev", "owner", "售后咨询");
        service.createConversation("dev", "owner", "售后咨询（2）");
        var conversation = service.createConversation("dev", "owner", null);
        String run = pending(conversation.id(), "request-1");
        var event = titleEvent(1, "售后咨询");
        var result = inTransaction(run, event);
        assertThat(service.getConversation("dev", "owner", conversation.id()).title()).isEqualTo("售后咨询（3）");
        assertThat(result.eventType()).isEqualTo("run.progress");
        assertThat(result.payload()).isEqualTo(java.util.Map.of("stage", "conversation_title", "summary", "会话标题已更新"));
        service.updateConversation("dev", "owner", conversation.id(), "手工标题", null);
        inTransaction(run, event);
        assertThat(service.getConversation("dev", "owner", conversation.id()).title()).isEqualTo("手工标题");
        var later = service.createConversation("dev", "owner", null);
        pending(later.id(), "earlier");
        String laterRun = pending(later.id(), "later");
        inTransaction(laterRun, titleEvent(1, "后续轮不应命名"));
        assertThat(service.getConversation("dev", "owner", later.id()).title()).isEmpty();
    }

    @Test
    void titleEventAllowsMissingTitleButRejectsWrongStageOrPhase() throws Exception {
        var optional = mapper.readValue("""
                {"contract_version":"customer-service-run-event/1","run_id":"agent-run","sequence":1,
                "event_type":"conversation.title","status":"RUNNING","occurred_at":"2026-10-27T00:00:00Z",
                "payload":{"stage":"conversation_title","public_summary":"会话标题已更新"}}
                """, CustomerServiceRunEvent.class);
        var conversation = service.createConversation("dev", "owner", null);
        inTransaction(pending(conversation.id(), "r1"), optional);
        assertThat(service.getConversation("dev", "owner", conversation.id()).title()).isEmpty();
        String valid = mapper.writeValueAsString(titleEvent(1, "主题"));
        assertThatThrownBy(() -> mapper.readValue(valid.replace("\"stage\":\"conversation_title\"", "\"stage\":\"intent\""), CustomerServiceRunEvent.class))
                .hasRootCauseInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> mapper.readValue(valid.replace("\"phase\":null", "\"phase\":\"STARTED\""), CustomerServiceRunEvent.class))
                .hasRootCauseInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void autoDuplicateStatementRetriesAndCommitsWithinSameTransaction() throws Exception {
        var conversation = service.createConversation("dev", "owner", null);
        String run = pending(conversation.id(), "r1");
        var racingRepository = spy(repository);
        doAnswer(call -> {
            if ("主题".equals(call.getArgument(4))) service.createConversation("dev", "owner", "主题");
            return call.callRealMethod();
        }).when(racingRepository).assignConversationTitle(any(), any(), any(), any(), any());
        var racingProjector = new CustomerServiceEventProjector(racingRepository, mapper);
        var event = titleEvent(1, "主题");
        new TransactionTemplate(new DataSourceTransactionManager(database))
                .execute(status -> racingProjector.project(run, "dev", event));
        assertThat(service.getConversation("dev", "owner", conversation.id()).title()).isEqualTo("主题（2）");
        assertThat(repository.findRun(run, "dev").lastEventSequence()).isEqualTo(1);
        assertThat(repository.listRunSteps(run)).hasSize(1);
    }

    @Test
    void casPreservesTitleSavedBetweenOwnerReadAndAutomaticUpdate() throws Exception {
        var conversation = service.createConversation("dev", "owner", null);
        String run = pending(conversation.id(), "r1");
        var racingRepository = spy(repository);
        doAnswer(call -> {
            service.updateConversation("dev", "owner", conversation.id(), "手工优先", null);
            return call.callRealMethod();
        }).when(racingRepository).assignConversationTitle(any(), any(), any(), any(), any());
        var event = titleEvent(1, "模型标题");
        var racingProjector = new CustomerServiceEventProjector(racingRepository, mapper);
        new TransactionTemplate(new DataSourceTransactionManager(database))
                .execute(status -> racingProjector.project(run, "dev", event));
        assertThat(service.getConversation("dev", "owner", conversation.id()).title()).isEqualTo("手工优先");
    }

    @Test
    void finalUniqueIndexRejectsConcurrentCreatesAfterBothPrechecksPass() throws Exception {
        var racingRepository = spy(repository);
        var barrier = new java.util.concurrent.CyclicBarrier(2);
        doAnswer(call -> {
            Object available = call.callRealMethod();
            barrier.await(5, java.util.concurrent.TimeUnit.SECONDS);
            return available;
        }).when(racingRepository).conversationTitleExists(any(), any(), any(), any());
        var racingService = new CustomerServiceApplicationService(racingRepository, mock(AiManagementMappers.class),
                new CustomerServicePendingRunCreator(racingRepository), mock(AiInvokeFacade.class));
        try (var executor = java.util.concurrent.Executors.newFixedThreadPool(2)) {
            java.util.concurrent.Callable<String> attempt = () -> {
                try { racingService.createConversation("dev", "owner", "并发名称"); return "CREATED"; }
                catch (TitleException error) { return error.code(); }
            };
            var first = executor.submit(attempt);
            var second = executor.submit(attempt);
            assertThat(java.util.List.of(first.get(10, java.util.concurrent.TimeUnit.SECONDS), second.get(10, java.util.concurrent.TimeUnit.SECONDS)))
                    .containsExactlyInAnyOrder("CREATED", "CUSTOMER_SERVICE_CONVERSATION_TITLE_DUPLICATE");
        }
        assertThat(repository.countConversations("dev", "owner", null)).isEqualTo(1);
    }

    @Test
    void duplicateRenameKeepsOriginalAndOtherDatabaseErrorsAreNotConverted() throws Exception {
        service.createConversation("dev", "1", "占用名称");
        var conversation = service.createConversation("dev", "1", "原名");
        mvc.perform(patch("/api/customer-service/conversations/" + conversation.id()).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\" 占用名称 \"}"))
                .andExpect(status().isConflict()).andExpect(jsonPath("$.code").value("CUSTOMER_SERVICE_CONVERSATION_TITLE_DUPLICATE"));
        assertThat(service.getConversation("dev", "1", conversation.id()).title()).isEqualTo("原名");
        var failingRepository = spy(repository);
        var unrelated = new org.springframework.dao.DuplicateKeyException("PRIMARY key failure");
        org.mockito.Mockito.doThrow(unrelated).when(failingRepository).insertConversation(any());
        var failingService = new CustomerServiceApplicationService(failingRepository, mock(AiManagementMappers.class),
                new CustomerServicePendingRunCreator(failingRepository), mock(AiInvokeFacade.class));
        assertThatThrownBy(() -> failingService.createConversation("dev", "1", "新名")).isSameAs(unrelated);
    }

    @Test
    void explicitTitleAndLostProjectionCasRemainUnchanged() throws Exception {
        var explicit = service.createConversation("dev", "owner", "显式标题");
        var run = pending(explicit.id(), "explicit");
        inTransaction(run, titleEvent(1, "模型标题"));
        assertThat(service.getConversation("dev", "owner", explicit.id()).title()).isEqualTo("显式标题");
        var untitled = service.createConversation("dev", "owner", null);
        String pendingRun = pending(untitled.id(), "untitled");
        assertThat(inTransaction(pendingRun, titleEvent(2, "不连续事件"))).isNull();
        assertThat(service.getConversation("dev", "owner", untitled.id()).title()).isEmpty();
    }

    @Test
    void autoTitleTrimsAndBoundsUnicodeWithoutSplittingCharacters() throws Exception {
        var conversation = service.createConversation("dev", "owner", null);
        String title = "😀".repeat(30);
        inTransaction(pending(conversation.id(), "r1"), titleEvent(1, "  " + title + "  "));
        assertThat(service.getConversation("dev", "owner", conversation.id()).title()).isEqualTo("😀".repeat(24));
    }

    private String pending(String conversation, String request) {
        var pending = new CustomerServicePendingRunCreator(repository).create(conversation, "dev", "问题", request, "release");
        repository.bindAgentRun(pending.run().id(), "agent-run", "RUNNING");
        return pending.run().id();
    }

    private CustomerServiceRunEvent titleEvent(long sequence, String title) throws Exception {
        return mapper.readValue("""
                {"contract_version":"customer-service-run-event/1","run_id":"agent-run","sequence":%s,
                "event_type":"conversation.title","status":"RUNNING","occurred_at":"2026-10-27T00:00:00Z",
                "payload":{"stage":"conversation_title","public_summary":"UNTRUSTED MODEL TITLE","conversation_title":"%s"}}
                """.formatted(sequence, title), CustomerServiceRunEvent.class);
    }

    private CustomerServiceEventProjector.PublicEvent inTransaction(String run, CustomerServiceRunEvent event) {
        return new TransactionTemplate(new DataSourceTransactionManager(database)).execute(status -> projector.project(run, "dev", event));
    }
}

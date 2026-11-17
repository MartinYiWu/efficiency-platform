package com.aiep.aihub.memory;

import com.aiep.aihub.api.memory.MemoryContracts;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.application.memory.ConversationScopeResolver;
import com.aiep.aihub.application.memory.MemoryActorProvider;
import com.aiep.aihub.application.memory.MemoryScopePolicy;
import com.aiep.aihub.application.memory.MemorySessionBindingService;
import com.aiep.aihub.facade.memory.DefaultMemoryFacade;
import com.aiep.aihub.repository.memory.MemoryMapper;
import com.aiep.identity.api.IdentityFacade;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DuplicateKeyException;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class MemorySessionBindingTest {
    private final IdentityFacade identity = mock(IdentityFacade.class);
    private final MemoryMapper mapper = mock(MemoryMapper.class);
    private final MemoryScopePolicy policy = new MemoryScopePolicy(identity, mock(MemoryActorProvider.class));
    private final MemorySessionBindingService bindings = new MemorySessionBindingService(mapper, policy, new ConversationScopeResolver());
    private final IdentityFacade.Subject actor = new IdentityFacade.Subject("t", "u", Set.of(), Set.of(), Set.of(), Set.of(), List.of(), "original");

    @BeforeEach void authenticateOriginalSession() {
        when(identity.refresh("t", "u", "original")).thenReturn(Optional.of(actor));
    }

    @Test void backfillsOldConversationFromTrustedBusinessTableWithoutTitleOrBody() {
        when(mapper.findOperationOwner(any(), any(), any())).thenReturn(owner("t", "u", "s"));
        when(mapper.insertSessionBinding(any())).thenReturn(1);
        var scope = bindings.bind(actor, "operations", "s");
        assertEquals("operations", scope.topLevelAgentId());
        var captured = org.mockito.ArgumentCaptor.forClass(MemoryMapper.SessionBindingPO.class);
        verify(mapper).insertSessionBinding(captured.capture());
        assertEquals("OPERATION_CONVERSATION", captured.getValue().originalObjectType());
        assertArrayEquals(bytes("s"), captured.getValue().originalObjectId());
        verify(mapper, never()).findCustomerServiceOwner(any(), any(), any());
    }

    @Test void everyReadRechecksSourceOwnerAndRejectsMissingOrForeignOwner() {
        assertCode("MEMORY_SCOPE_DENIED", () -> bindings.bind(actor, "operations", "s"));
        when(mapper.findOperationOwner(any(), any(), any())).thenReturn(owner("t", "u ", "s"));
        assertCode("MEMORY_SCOPE_DENIED", () -> bindings.bind(actor, "operations", "s"));
        verify(mapper, never()).insertSessionBinding(any());
        verify(mapper, never()).findSessionBinding(any(), any(), any());
    }

    @Test void existingBindingCannotChangeAgentEvenWhenOtherBusinessHasSameId() {
        when(mapper.findCustomerServiceOwner(any(), any(), any())).thenReturn(owner("t", "u", "s"));
        when(mapper.findSessionBinding(any(), any(), any())).thenReturn(binding("operations"));
        assertCode("MEMORY_SESSION_BINDING_CONFLICT", () -> bindings.bind(actor, "customer-service", "s"));
        verify(mapper, never()).insertSessionBinding(any());
    }

    @Test void concurrentFirstBindingReadsWinnerAndNeverUpdatesItsOwnership() {
        when(mapper.findOperationOwner(any(), any(), any())).thenReturn(owner("t", "u", "s"));
        when(mapper.findSessionBinding(any(), any(), any())).thenReturn(null, binding("operations"));
        when(mapper.insertSessionBinding(any())).thenThrow(new DuplicateKeyException("unique"));
        assertEquals("s", bindings.bind(actor, "operations", "s").sessionId());
        verify(mapper, times(2)).findSessionBinding(any(), any(), any());
    }

    @Test void concurrentWinnerFromOtherAgentIsConflictAndZeroInsertIsNotSuccess() {
        when(mapper.findOperationOwner(any(), any(), any())).thenReturn(owner("t", "u", "s"));
        when(mapper.findSessionBinding(any(), any(), any())).thenReturn(null, binding("customer-service"));
        when(mapper.insertSessionBinding(any())).thenThrow(new DuplicateKeyException("unique"));
        assertCode("MEMORY_SESSION_BINDING_CONFLICT", () -> bindings.bind(actor, "operations", "s"));
        reset(mapper);
        when(mapper.findOperationOwner(any(), any(), any())).thenReturn(owner("t", "u", "s"));
        assertCode("MEMORY_SESSION_BINDING_CONFLICT", () -> bindings.bind(actor, "operations", "s"));
    }

    @Test void hrAndUnknownAgentsDoNotReachBindingOrSourceQueries() {
        assertCode("MEMORY_SCOPE_DENIED", () -> bindings.bind(actor, "hr", "s"));
        assertCode("MEMORY_SCOPE_DENIED", () -> bindings.bind(actor, "unknown", "s"));
        verifyNoInteractions(mapper);
        var hr = new ConversationScopeResolver().taskOnly(new com.aiep.aihub.application.operation.OperationActor("t", "u"), "hr");
        bindings.require(actor, hr);
        verifyNoInteractions(mapper);
    }

    @Test void allDeferredFacadeOperationsReturnStableFeatureDisabledWithoutFakeSuccess() {
        var facade = new DefaultMemoryFacade(policy);
        var scope = new MemoryScopeDTO("t", "u", "operations", "operations", "CONVERSATION", "s");
        var command = new MemoryContracts.PreferenceCommand(scope, "response.language", "zh-CN", 0, "request-1", null);
        assertCode("FEATURE_DISABLED", () -> facade.listPreferences(actor, scope, Set.of("response.language")));
        assertCode("FEATURE_DISABLED", () -> facade.savePreference(actor, command));
        assertCode("FEATURE_DISABLED", () -> facade.correctPreference(actor, "id", command));
        assertCode("FEATURE_DISABLED", () -> facade.forget(actor, "id", new MemoryContracts.ForgetCommand(scope, 0, "request-2")));
        assertCode("FEATURE_DISABLED", () -> facade.assemblePacket(actor, new MemoryContracts.Execution(scope, "task", "execution")));
        verifyNoInteractions(mapper);
    }

    @Test void xmlBindsAllScopeDimensionsAndSourceQueriesUseBinaryExactComparisons() throws Exception {
        var configuration = new org.apache.ibatis.session.Configuration();
        try (var stream = getClass().getClassLoader().getResourceAsStream("mapper/memory/MemoryMapper.xml")) {
            new org.apache.ibatis.builder.xml.XMLMapperBuilder(stream, configuration, "mapper/memory/MemoryMapper.xml", configuration.getSqlFragments()).parse();
        }
        for (String name : List.of("findOperationOwner", "findCustomerServiceOwner")) {
            String sql = configuration.getMappedStatement(MemoryMapper.class.getName() + "." + name).getBoundSql(null).getSql();
            assertEquals(3, sql.split("CAST\\(", -1).length - 1);
            assertFalse(sql.contains("title"));
            assertFalse(sql.contains("content"));
        }
        var method = MemorySessionBindingService.class.getMethod("bind", IdentityFacade.Subject.class, String.class, String.class);
        assertNotNull(method.getAnnotation(org.springframework.transaction.annotation.Transactional.class));
    }

    @Test void publicCommandAndResultJsonHaveStableNamesAndNeverCarrySessionCredentials() throws Exception {
        var json = new com.fasterxml.jackson.databind.ObjectMapper();
        var scope = new MemoryScopeDTO("t", "u", "operations", "operations", "CONVERSATION", "s");
        var command = new MemoryContracts.PreferenceCommand(scope, "response.language", "zh-CN", 1, "request", null);
        var tree = json.readTree(json.writeValueAsString(command));
        assertEquals("response.language", tree.path("fieldKey").asText());
        assertEquals(1, tree.path("expectedRevision").asLong());
        assertEquals("operations", tree.path("scope").path("top_level_agent_id").asText());
        assertFalse(tree.has("tenantId"));
        assertFalse(tree.has("userId"));
        String serialized = json.writeValueAsString(new MemoryContracts.Preference("id", "version", scope, "response.language", "zh-CN", 1));
        assertFalse(serialized.contains("sessionRef"));
        assertFalse(serialized.contains("original"));
        assertFalse(serialized.contains("contentHmac"));
    }

    private MemoryMapper.SourceOwnerPO owner(String t, String u, String s) { return new MemoryMapper.SourceOwnerPO(bytes(t), bytes(u), bytes(s)); }
    private MemoryMapper.SessionBindingPO binding(String agent) {
        return new MemoryMapper.SessionBindingPO(bytes("t"), bytes("binding"), bytes("u"), agent, agent, bytes("s"), "CONVERSATION",
                "operations".equals(agent) ? "OPERATION_CONVERSATION" : "CUSTOMER_SERVICE_CONVERSATION", bytes("s"));
    }
    private byte[] bytes(String value) { return MemoryMapper.identity(value); }
    private void assertCode(String code, org.junit.jupiter.api.function.Executable action) {
        assertEquals(code, assertThrows(MemoryContracts.MemoryException.class, action).code());
    }
}

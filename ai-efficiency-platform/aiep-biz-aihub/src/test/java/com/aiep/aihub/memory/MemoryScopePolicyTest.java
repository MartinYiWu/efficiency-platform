package com.aiep.aihub.memory;

import com.aiep.aihub.api.memory.MemoryContracts;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.application.memory.ConversationScopeResolver;
import com.aiep.aihub.application.memory.MemoryActorProvider;
import com.aiep.aihub.application.memory.MemoryScopePolicy;
import com.aiep.aihub.application.operation.OperationActor;
import com.aiep.aihub.domain.memory.MemoryKey;
import com.aiep.identity.api.IdentityFacade;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class MemoryScopePolicyTest {
    private final IdentityFacade identity = mock(IdentityFacade.class);
    private final MemoryActorProvider actors = mock(MemoryActorProvider.class);
    private final MemoryScopePolicy policy = new MemoryScopePolicy(identity, actors);
    private final IdentityFacade.Subject actor = subject("t", "u", "original", Set.of(), List.of());
    private final ConversationScopeResolver scopes = new ConversationScopeResolver();

    @Test void i01TenantAndI02UserAreExactAndConfigurationAdminCannotReadOthers() {
        allow(actor);
        policy.require(actor, scope("t", "u", "operations", "s1"), Set.of("response.language"));
        for (var scope : List.of(scope("t2", "u", "operations", "s1"),
                scope("t", "other", "operations", "s1"), scope("t ", "u", "operations", "s1"))) {
            assertCode("MEMORY_SCOPE_DENIED", () -> policy.require(actor, scope, Set.of("response.language")));
        }
        var admin = subject("t", "admin", "original", Set.of("hr:config:edit"),
                List.of(new IdentityFacade.GrantScope("hr:config:edit", "d", null, null)));
        allow(admin);
        assertCode("MEMORY_SCOPE_DENIED", () -> policy.require(admin, scope("t", "u", "operations", "s"), Set.of("response.language")));
    }

    @Test void i03AgentsSeparateSameFieldAndI04SessionsShareOnlyPrivateKey() {
        var first = scope("t", "u", "operations", "s1");
        var second = scope("t", "u", "operations", "s2");
        var customer = scope("t", "u", "customer-service", "s1");
        assertEquals(MemoryKey.preference(first, "response.language"), MemoryKey.preference(second, "response.language"));
        assertNotEquals(MemoryKey.preference(first, "response.language"), MemoryKey.preference(customer, "response.language"));
        assertNotEquals(first.historyKey(), second.historyKey());
        assertFalse(policy.canReadHistory(first, second));
        assertFalse(policy.canReadHistory(first, customer));
        assertTrue(policy.canReadHistory(first, first));
    }

    @Test void i05HrTaskOnlyNeverCreatesHistoryOrCrossTaskBucket() {
        var hr = scopes.taskOnly(new OperationActor("t", "u"), "hr");
        assertNull(hr.historyKey());
        assertFalse(policy.canReadHistory(hr, hr));
        assertThrows(IllegalArgumentException.class, () -> scopes.conversation(new OperationActor("t", "u"), "hr", "s", "t", "u", "hr"));
        assertNull(scopes.taskOnly(new OperationActor("t", "u"), "operations").historyKey());
        allow(actor);
        policy.require(actor, hr, Set.of("response.language"));
    }

    @Test void i06SourcePermissionUsesOneExactTupleNeverIndependentUnions() {
        var grants = List.of(new IdentityFacade.GrantScope("hr:candidate:original", "d1", null, "c1"),
                new IdentityFacade.GrantScope("hr:candidate:read", "d2", null, "c2"));
        var hr = subject("t", "u", "original", Set.of("hr:candidate:original", "hr:candidate:read"), grants);
        allow(hr);
        policy.requireHrSource(hr, "hr:candidate:original", "d1", null, "c1");
        assertCode("MEMORY_SCOPE_DENIED", () -> policy.requireHrSource(hr, "hr:candidate:original", "d2", null, "c2"));
        assertCode("MEMORY_SCOPE_DENIED", () -> policy.requireHrSource(hr, "hr:config:edit", "d1", null, "c1"));
        var revoked = subject("t", "u", "original", Set.of(), List.of());
        allow(revoked);
        assertCode("MEMORY_SCOPE_DENIED", () -> policy.requireHrSource(hr, "hr:candidate:original", "d1", null, "c1"));
    }

    @Test void i07OriginalSessionRevocationNeverBorrowsAnotherLogin() {
        when(identity.refresh("t", "u", "original")).thenReturn(Optional.empty());
        when(identity.refresh("t", "u")).thenReturn(Optional.of(subject("t", "u", "other", Set.of(), List.of())));
        assertCode("MEMORY_IDENTITY_REQUIRED", () -> policy.require(actor, scope("t", "u", "operations", "s"), Set.of("response.language")));
        verify(identity, never()).refresh("t", "u");
        when(identity.refresh("t", "u", "original")).thenReturn(Optional.of(subject("t", "u", "other", Set.of(), List.of())));
        assertCode("MEMORY_IDENTITY_REQUIRED", () -> policy.require(actor, scope("t", "u", "operations", "s"), Set.of("response.language")));
    }

    @Test void currentActorComesFromProviderAndOnlyThreeFieldsAreAllowed() {
        when(actors.current()).thenReturn(new OperationActor("t", "u", "original"));
        allow(actor);
        assertEquals(actor, policy.currentActor());
        policy.require(actor, scope("t", "u", "operations", "s"), Set.of("response.language", "response.detail_level", "response.format"));
        assertCode("FEATURE_DISABLED", () -> policy.require(actor, scope("t", "u", "operations", "s"), Set.of("profile.salary")));
        assertThrows(IllegalArgumentException.class, () -> MemoryKey.preference(scope("t", "u", "operations", "s"), "response.language "));
        assertThrows(IllegalArgumentException.class, () -> new MemoryScopeDTO("t", "u", "unknown", "unknown", "CONVERSATION", "s"));
    }

    @Test void identitySupports128UnicodeCharactersAndPreservesExactBytes() {
        String emoji = "😀".repeat(128);
        assertDoesNotThrow(() -> new OperationActor(emoji, emoji, "original"));
        var scope = scope(emoji, emoji, "operations", emoji);
        assertEquals(emoji, scopes.envelope(scope).scope().userId());
        assertEquals(530, MemoryKey.preference(scope, "response.language").scopeId().length);
        assertNotEquals(MemoryKey.preference(scope("t", "u", "operations", "s"), "response.language"),
                MemoryKey.preference(scope("t", "u ", "operations", "s"), "response.language"));
        assertThrows(IllegalArgumentException.class, () -> new OperationActor("t", "\ud800"));
        assertThrows(IllegalArgumentException.class, () -> scope("t", "u", "operations", "x".repeat(129)));
    }

    @Test void unicode127And128TraverseActorScopeAndEnvelopeWithoutTruncation() {
        for (int count : List.of(127, 128)) {
            String emoji = "😀".repeat(count);
            var actor = new OperationActor(emoji, emoji, "original");
            var scope = scopes.conversation(actor, "operations", emoji, emoji, emoji, "operations");
            var envelope = scopes.envelope(scope);
            assertEquals(emoji, envelope.scope().tenantId());
            assertEquals(emoji, envelope.scope().userId());
            assertEquals(emoji, envelope.scope().sessionId());
            assertEquals(8 + 4 * count + "operations".length(), MemoryKey.preference(scope, "response.language").scopeId().length);
        }
    }

    @Test void unicode129AndUnpairedSurrogatesAreRejectedAtEveryIdentityEntry() {
        for (String invalid : List.of("😀".repeat(129), "\ud800", "\udc00", "x\ud800y")) {
            assertThrows(IllegalArgumentException.class, () -> new OperationActor(invalid, "u", "original"));
            assertThrows(IllegalArgumentException.class, () -> new OperationActor("t", invalid, "original"));
            assertThrows(IllegalArgumentException.class, () -> scope(invalid, "u", "operations", "s"));
            assertThrows(IllegalArgumentException.class, () -> scope("t", invalid, "operations", "s"));
            assertThrows(IllegalArgumentException.class, () -> scope("t", "u", "operations", invalid));
            assertThrows(IllegalArgumentException.class, () -> new com.aiep.platformai.api.dto.MemoryContextEnvelope.Scope(invalid, "u", "operations", "operations", "CONVERSATION", "s"));
            assertThrows(IllegalArgumentException.class, () -> new com.aiep.platformai.api.dto.MemoryContextEnvelope.Scope("t", invalid, "operations", "operations", "CONVERSATION", "s"));
            assertThrows(IllegalArgumentException.class, () -> new com.aiep.platformai.api.dto.MemoryContextEnvelope.Scope("t", "u", "operations", "operations", "CONVERSATION", invalid));
            assertThrows(IllegalArgumentException.class, () -> new MemoryKey(invalid, "u", "operations", "response.language"));
            assertThrows(IllegalArgumentException.class, () -> new MemoryKey("t", invalid, "operations", "response.language"));
            assertThrows(IllegalArgumentException.class, () -> com.aiep.aihub.repository.memory.MemoryMapper.identity(invalid));
        }
    }

    private void allow(IdentityFacade.Subject subject) {
        when(identity.refresh(subject.tenantId(), subject.userId(), subject.sessionRef())).thenReturn(Optional.of(subject));
    }
    private MemoryScopeDTO scope(String t, String u, String agent, String session) {
        return new MemoryScopeDTO(t, u, agent, agent, "CONVERSATION", session);
    }
    private IdentityFacade.Subject subject(String t, String u, String ref, Set<String> permissions, List<IdentityFacade.GrantScope> grants) {
        return new IdentityFacade.Subject(t, u, Set.of("d1", "d2"), permissions, Set.of(), Set.of("c1", "c2"), grants, ref);
    }
    private void assertCode(String code, org.junit.jupiter.api.function.Executable action) {
        assertEquals(code, assertThrows(MemoryContracts.MemoryException.class, action).code());
    }
}

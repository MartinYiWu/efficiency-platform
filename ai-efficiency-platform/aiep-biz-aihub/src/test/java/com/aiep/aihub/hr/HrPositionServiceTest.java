package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.api.hr.HrPositionContracts.CreatePosition;
import com.aiep.aihub.api.hr.HrPositionContracts.Position;
import com.aiep.aihub.application.hr.HrPositionService;
import com.aiep.aihub.repository.hr.HrPositionRepository;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Set;
import org.junit.jupiter.api.Test;

class HrPositionServiceTest {
    private final HrPositionRepository repository = mock(HrPositionRepository.class);
    private final HrPositionService service = new HrPositionService(repository,
            Clock.fixed(Instant.parse("2026-11-11T02:00:00Z"), ZoneOffset.UTC));
    private final HrActor actor = new HrActor("tenant", "hr-user", Set.of("engineering"),
            Set.of("hr:position:edit", "hr:position:read", "hr:position:publish"));

    @Test void creates_draft_with_server_owner_and_normalized_name() {
        Position position = service.create(actor, new CreatePosition("  后端工程师  ", "TECHNOLOGY", "engineering", "P6", null));
        assertEquals("后端工程师", position.name());
        assertEquals("DRAFT", position.status());
        assertEquals("tenant", position.tenantId());
        assertEquals("hr-user", position.createdBy());
        assertNull(position.configVersion());
        verify(repository).insert(position);
    }

    @Test void rejects_permission_or_department_scope_before_writing() {
        assertThrows(RuntimeException.class, () -> service.create(new HrActor("tenant", "u", Set.of("engineering"), Set.of()),
                new CreatePosition("岗位", "TECHNOLOGY", "engineering", "P6", null)));
        assertThrows(RuntimeException.class, () -> service.create(actor,
                new CreatePosition("岗位", "TECHNOLOGY", "other-department", "P6", null)));
        verifyNoInteractions(repository);
    }

    @Test void invisible_position_is_not_returned_and_does_not_leak_existence() {
        when(repository.find("tenant", "other-position")).thenReturn(new Position("other-position", "tenant", "销售", "SALES",
                "sales", "P6", "SA-000001", "ACTIVE", "v1.0", "ctx-1", "other-user", Instant.now(), 1));
        assertThrows(RuntimeException.class, () -> service.get(actor, "other-position"));
    }

    @Test void invalid_family_and_blank_name_never_create_records() {
        assertThrows(RuntimeException.class, () -> service.create(actor,
                new CreatePosition("岗位", "invented", "engineering", "P6", null)));
        assertThrows(RuntimeException.class, () -> service.create(actor,
                new CreatePosition(" ", "TECHNOLOGY", "engineering", "P6", null)));
        verifyNoInteractions(repository);
    }
}

package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.application.hr.HrBusinessException;
import com.aiep.aihub.web.hr.HrActorResolver;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;

class HrActorResolverTest {
    @Test void browser_headers_cannot_claim_department_or_hr_privileges() {
        var request=new MockHttpServletRequest();request.setRemoteAddr("127.0.0.1");
        request.addHeader("X-Tenant-ID","dev");request.addHeader("X-User-ID","1");request.addHeader("X-HR-Role","admin");
        assertThrows(HrBusinessException.class,()->new HrActorResolver(false,"","","","").resolve(request));
    }
    @Test void trusted_actor_needs_matching_authenticated_principal() {
        var request=new MockHttpServletRequest();HrActor actor=new HrActor("t","1",Set.of("d"),Set.of("hr:candidate:read"));
        request.setAttribute(HrActor.class.getName(),actor);
        var resolver=new HrActorResolver(false,"","","","");
        assertThrows(HrBusinessException.class,()->resolver.resolve(request));
        request.setUserPrincipal(()->"1");assertEquals(actor,resolver.resolve(request));
    }
    @Test void explicit_development_actor_is_limited_to_local_requests() {
        var resolver=new HrActorResolver(true,"t","1","d","hr:candidate:read");var request=new MockHttpServletRequest();
        request.setRemoteAddr("127.0.0.1");assertEquals(Set.of("d"),resolver.resolve(request).departmentIds());
        request.setRemoteAddr("192.0.2.1");assertThrows(HrBusinessException.class,()->resolver.resolve(request));
    }
}

package com.aiep;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;

import java.lang.reflect.Method;
import jakarta.servlet.Filter;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

class BootApplicationTest {

    @Test
    void exposes_boot_application_entrypoint() {
        assertThatCode(() -> Class.forName("com.aiep.BootApplication"))
                .doesNotThrowAnyException();
    }

    @Test
    void creates_standard_success_response() throws Exception {
        Class<?> responseType = Class.forName("com.aiep.platformcore.api.ApiResponse");
        Method success = responseType.getMethod("success", Object.class);
        Object response = success.invoke(null, "pong");

        assertThat(responseType.getMethod("code").invoke(response)).isEqualTo("SUCCESS");
        assertThat(responseType.getMethod("data").invoke(response)).isEqualTo("pong");
    }

    @Test
    void stores_request_trace_id_in_request_context() throws Exception {
        Class<?> holderType = Class.forName("com.aiep.platformcore.domain.TraceIdHolder");
        Method set = holderType.getMethod("set", String.class);
        Method current = holderType.getMethod("current");
        Method clear = holderType.getMethod("clear");

        set.invoke(null, "trace-test");
        assertThat(current.invoke(null)).isEqualTo("trace-test");
        clear.invoke(null);
        assertThat(current.invoke(null)).isNull();
    }

    @Test
    void echoes_request_trace_id_to_response() throws Exception {
        Filter filter = (Filter) Class.forName("com.aiep.platformcore.config.TraceIdFilter")
                .getConstructor().newInstance();
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("X-Trace-Id", "trace-from-client");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, new MockFilterChain());

        assertThat(response.getHeader("X-Trace-Id")).isEqualTo("trace-from-client");
    }

    @Test
    void exposes_platform_ping_response() throws Exception {
        Class<?> controllerType = Class.forName("com.aiep.BootstrapController");
        Object controller = controllerType.getConstructor().newInstance();
        Object response = controllerType.getMethod("ping").invoke(controller);

        assertThat(response.getClass().getMethod("code").invoke(response)).isEqualTo("SUCCESS");
        assertThat(response.getClass().getMethod("data").invoke(response)).isEqualTo("pong");
    }
}

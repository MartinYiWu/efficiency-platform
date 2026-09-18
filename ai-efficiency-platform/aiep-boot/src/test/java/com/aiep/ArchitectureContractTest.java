package com.aiep;

import static org.assertj.core.api.Assertions.assertThat;

import java.lang.reflect.Field;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

class ArchitectureContractTest {

    @Test
    void exposes_one_api_facade_anchor_for_each_non_boot_module() throws Exception {
        for (String className : Set.of(
                "com.aiep.platformcore.api.CoreFacade",
                "com.aiep.platformcontent.api.ContentFacade",
                "com.aiep.platformai.api.AiInvokeFacade",
                "com.aiep.platformfile.api.FileFacade",
                "com.aiep.platformtask.api.TaskFacade",
                "com.aiep.identity.api.IdentityFacade",
                "com.aiep.knowledge.api.KnowledgeFacade",
                "com.aiep.asset.api.AssetFacade",
                "com.aiep.aihub.api.AiHubFacade",
                "com.aiep.system.api.SystemFacade",
                "com.aiep.workspace.api.WorkspaceFacade",
                "com.aiep.analytics.api.AnalyticsFacade")) {
            assertThat(Class.forName(className).isInterface()).isTrue();
        }
    }

    @Test
    void centralizes_exactly_seven_agent_business_endpoint_constants() throws Exception {
        Class<?> endpoints = Class.forName("com.aiep.platformai.agent.AgentEndpoints");
        Set<String> endpointValues = Stream.of(endpoints.getFields())
                .map(this::readStringConstant)
                .collect(Collectors.toSet());

        assertThat(endpointValues).containsExactlyInAnyOrder(
                "/text/generate", "/chat/stream", "/skill/execute", "/kb/qa",
                "/kb/ingest", "/task/{task_id}", "/kb/vectors");
    }

    @Test
    void exposes_the_seven_agent_operations_through_ai_invoke_facade() throws Exception {
        Class<?> facade = Class.forName("com.aiep.platformai.api.AiInvokeFacade");
        Set<String> operationNames = Stream.of(facade.getDeclaredMethods())
                .map(method -> method.getName())
                .collect(Collectors.toSet());

        assertThat(operationNames).containsExactlyInAnyOrder(
                "generateText", "streamChat", "executeSkill", "streamKbQa",
                "submitIngest", "queryTask", "deleteVectors");
    }

    @Test
    void exposes_java_owned_task_state_machine() throws Exception {
        Class<?> taskStatus = Class.forName("com.aiep.platformtask.api.TaskStatus");
        assertThat(taskStatus.isEnum()).isTrue();
        assertThat(Stream.of(taskStatus.getEnumConstants()).map(Object::toString))
                .containsExactlyInAnyOrder("PENDING", "RUNNING", "SUCCESS", "FAILED");
    }

    private String readStringConstant(Field field) {
        try {
            return (String) field.get(null);
        } catch (IllegalAccessException exception) {
            throw new AssertionError(exception);
        }
    }
}

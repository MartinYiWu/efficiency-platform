package com.aiep;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

class ArchitectureRulesTest {

    @Test
    void exposes_non_negotiable_architecture_rules() throws Exception {
        Class<?> rules = Class.forName("com.aiep.ArchitectureRules");
        Set<String> methodNames = Stream.of(rules.getDeclaredMethods())
                .map(method -> method.getName())
                .collect(Collectors.toSet());

        assertThat(methodNames).contains(
                "platformAndIdentityDoNotDependOnBusiness",
                "businessLayersDoNotDependOnAggregation",
                "l2DependenciesAreRestricted",
                "controllersDoNotAccessRepositories",
                "apiDoesNotExposeRepositories",
                "onlyAgentPackageUsesWebClient");
    }
}

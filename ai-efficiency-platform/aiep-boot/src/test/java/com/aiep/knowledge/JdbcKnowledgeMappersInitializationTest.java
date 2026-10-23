package com.aiep.knowledge;

import static org.assertj.core.api.Assertions.assertThatCode;

import com.aiep.knowledge.repository.JdbcKnowledgeMappers;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

class JdbcKnowledgeMappersInitializationTest {
    @Test
    void initializesAllRecordMappersWithoutConstructorAmbiguity() {
        assertThatCode(() -> new JdbcKnowledgeMappers(new JdbcTemplate()))
                .doesNotThrowAnyException();
    }
}

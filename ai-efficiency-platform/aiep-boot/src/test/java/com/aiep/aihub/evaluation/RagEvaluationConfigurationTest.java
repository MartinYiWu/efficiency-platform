package com.aiep.aihub.evaluation;

import static org.assertj.core.api.Assertions.assertThat;

import com.aiep.aihub.config.RagEvaluationConfiguration;
import java.util.concurrent.ExecutorService;
import org.junit.jupiter.api.Test;

class RagEvaluationConfigurationTest {
    @Test
    void usesOneBackgroundWorkerToAvoidModelTrafficBursts() throws Exception {
        ExecutorService executor = new RagEvaluationConfiguration().ragEvaluationExecutor();
        try {
            assertThat(executor.submit(() -> Thread.currentThread().getName()).get())
                    .startsWith("rag-evaluation-");
        } finally {
            executor.close();
        }
    }
}

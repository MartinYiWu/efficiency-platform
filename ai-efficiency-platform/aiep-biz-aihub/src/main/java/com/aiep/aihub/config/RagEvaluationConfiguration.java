package com.aiep.aihub.config;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RagEvaluationConfiguration {
    @Bean(name = "ragEvaluationExecutor", destroyMethod = "close")
    public ExecutorService ragEvaluationExecutor() {
        return Executors.newSingleThreadExecutor(Thread.ofVirtual().name("rag-evaluation-", 0).factory());
    }
}

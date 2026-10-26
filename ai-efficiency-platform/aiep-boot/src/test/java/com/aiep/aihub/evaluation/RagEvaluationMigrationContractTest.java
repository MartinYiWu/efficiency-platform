package com.aiep.aihub.evaluation;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

class RagEvaluationMigrationContractTest {

    @Test
    void createsEvaluationTablesAndRecoveryScripts() throws Exception {
        Path migrationRoot = Path.of("..", "sql", "migration");
        Path migration = migrationRoot.resolve("V1.1.10__customer_service_rag_evaluation.sql");
        Path precheck = migrationRoot.resolve("manual/M__1.1.10__customer_service_rag_evaluation_precheck.sql");
        Path rollback = migrationRoot.resolve("rollback/R__V1.1.10__customer_service_rag_evaluation.sql");

        assertThat(migration).exists();
        assertThat(precheck).exists();
        assertThat(rollback).exists();
        String ddl = Files.readString(migration);
        assertThat(ddl).contains(
                "CREATE TABLE ai_rag_eval_dataset",
                "CREATE TABLE ai_rag_eval_case",
                "CREATE TABLE ai_rag_eval_run",
                "CREATE TABLE ai_rag_eval_case_result",
                "UNIQUE KEY uk_ai_rag_eval_case_no (dataset_id, case_no)",
                "KEY idx_ai_rag_eval_run_dataset_created (dataset_id, created_at)",
                "KEY idx_ai_rag_eval_result_run_passed (run_id, passed)");
    }
}

package com.aiep.aihub.repository.evaluation;

import com.aiep.aihub.application.evaluation.RagEvaluationModels.CaseResult;
import com.aiep.aihub.application.evaluation.RagEvaluationModels.Dataset;
import com.aiep.aihub.application.evaluation.RagEvaluationModels.EvaluationCase;
import com.aiep.aihub.application.evaluation.RagEvaluationModels.EvaluationRun;
import java.time.Instant;
import java.util.List;

public interface RagEvaluationRepository {
    Dataset createDataset(Dataset value);
    List<Dataset> listDatasets();
    Dataset findDataset(String id);
    int upsertCases(String datasetId, List<EvaluationCase> values);
    List<EvaluationCase> listCases(String datasetId);
    List<EvaluationCase> listEnabledCases(String datasetId);
    EvaluationRun createRun(EvaluationRun value);
    void markRunning(String id, Instant startedAt);
    void saveResult(CaseResult value);
    void completeRun(EvaluationRun value);
    EvaluationRun findRun(String id);
    List<EvaluationRun> listRuns(String datasetId);
    List<CaseResult> listResults(String runId);
}

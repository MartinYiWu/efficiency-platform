package com.aiep.aihub.web.management;

import com.aiep.aihub.application.evaluation.RagEvaluationModels.Dataset;
import com.aiep.aihub.application.evaluation.RagEvaluationModels.EvaluationCase;
import com.aiep.aihub.application.evaluation.RagEvaluationModels.EvaluationRun;
import com.aiep.aihub.application.evaluation.RagEvaluationService;
import com.aiep.aihub.application.evaluation.RagEvaluationService.CaseInput;
import com.aiep.aihub.application.evaluation.RagEvaluationService.CreateDatasetRequest;
import com.aiep.aihub.application.evaluation.RagEvaluationService.DatasetDetail;
import com.aiep.aihub.application.evaluation.RagEvaluationService.ImportResult;
import com.aiep.aihub.application.evaluation.RagEvaluationService.RunComparison;
import com.aiep.aihub.application.evaluation.RagEvaluationService.RunDetail;
import com.aiep.aihub.application.evaluation.RagEvaluationService.StartRunRequest;
import com.aiep.platformcore.api.ApiResponse;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/aihub/rag-evaluations")
public class RagEvaluationController {
    private final RagEvaluationService service;

    public RagEvaluationController(RagEvaluationService service) {
        this.service = service;
    }

    @GetMapping("/datasets")
    public ApiResponse<List<Dataset>> datasets() {
        return ApiResponse.success(service.listDatasets());
    }

    @PostMapping("/datasets")
    public ApiResponse<Dataset> createDataset(@RequestBody CreateDatasetRequest request) {
        return ApiResponse.success(service.createDataset(request));
    }

    @GetMapping("/datasets/{id}")
    public ApiResponse<DatasetDetail> dataset(@PathVariable String id) {
        return ApiResponse.success(service.getDataset(id));
    }

    @PostMapping("/datasets/{id}/cases")
    public ApiResponse<EvaluationCase> createCase(@PathVariable String id, @RequestBody CaseInput request) {
        return ApiResponse.success(service.createCase(id, request));
    }

    @PutMapping("/datasets/{id}/cases/{caseId}")
    public ApiResponse<EvaluationCase> updateCase(@PathVariable String id, @PathVariable String caseId,
                                                  @RequestBody CaseInput request) {
        return ApiResponse.success(service.updateCase(id, caseId, request));
    }

    @PostMapping("/datasets/{id}/cases/import")
    public ApiResponse<ImportResult> importCases(@PathVariable String id, @RequestBody List<CaseInput> request) {
        return ApiResponse.success(service.importCases(id, request));
    }

    @PostMapping("/runs")
    public ApiResponse<EvaluationRun> startRun(@RequestBody StartRunRequest request) {
        return ApiResponse.success(service.startRun(request));
    }

    @GetMapping("/runs")
    public ApiResponse<List<EvaluationRun>> runs(@RequestParam String datasetId) {
        return ApiResponse.success(service.listRuns(datasetId));
    }

    @GetMapping("/runs/{id}")
    public ApiResponse<RunDetail> run(@PathVariable String id) {
        return ApiResponse.success(service.getRun(id));
    }

    @GetMapping("/runs/compare")
    public ApiResponse<RunComparison> compare(@RequestParam String baselineRunId,
                                               @RequestParam String candidateRunId) {
        return ApiResponse.success(service.compareRuns(baselineRunId, candidateRunId));
    }
}

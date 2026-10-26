import { describe, expect, it } from 'vitest';

import { evaluationDatasetSchema, evaluationRunDetailSchema } from './evaluationSchemas';

describe('RAG evaluation contracts', () => {
  it('parses a dataset and nullable not-applicable metrics', () => {
    expect(
      evaluationDatasetSchema.parse({
        id: 'dataset-1',
        name: '研发规范',
        description: null,
        agentKey: 'customer-service',
        status: 'ACTIVE',
        caseCount: 18,
        createdAt: '2026-10-26T00:00:00Z',
        updatedAt: '2026-10-26T01:00:00Z',
      }).caseCount,
    ).toBe(18);

    expect(
      evaluationRunDetailSchema.parse({
        run: {
          id: 'run-1', datasetId: 'dataset-1', agentKey: 'customer-service',
          agentVersionId: 'av-1', ragPolicyVersionId: 'rp-1',
          knowledgeBindings: [{ knowledgeBaseId: 'kb-1', indexReleaseId: 'ir-1' }],
          status: 'SUCCEEDED', totalCount: 1, passedCount: 1, failedCount: 0,
          metrics: {
            executionSuccessRate: 1, answerModeAccuracy: 1, expectedFactRecall: null,
            prohibitedFactRate: null, sourceRecallAtK: null, citationComplianceRate: null,
            versionAccuracy: null, casePassRate: 1, latencyP50Ms: 120, latencyP95Ms: 120,
          }, failureCode: null, failureMessage: null,
          createdAt: '2026-10-26T00:00:00Z', startedAt: '2026-10-26T00:00:01Z',
          finishedAt: '2026-10-26T00:00:02Z',
        },
        cases: [],
        results: [],
      }).run.metrics?.expectedFactRecall,
    ).toBeNull();
  });
});

import { z } from 'zod';

export const evaluationDatasetSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().nullable(),
  agentKey: z.string(),
  status: z.enum(['DRAFT', 'ACTIVE', 'ARCHIVED']),
  caseCount: z.number().int().nonnegative(),
  createdAt: z.string(),
  updatedAt: z.string(),
}).strict();

export const evaluationCaseSchema = z.object({
  id: z.string(),
  datasetId: z.string(),
  caseNo: z.string(),
  question: z.string(),
  expectedAnswerMode: z.enum(['COMPANY_KNOWLEDGE', 'MIXED', 'GENERAL_ADVICE', 'INSUFFICIENT_EVIDENCE']),
  expectedFacts: z.array(z.string()),
  expectedFactAlternatives: z.record(z.string(), z.array(z.string())).optional(),
  prohibitedFacts: z.array(z.string()),
  expectedDocumentTitles: z.array(z.string()),
  expectedDocumentVersionIds: z.array(z.string()),
  minCitationCount: z.number().int().nonnegative(),
  tags: z.array(z.string()),
  enabled: z.boolean(),
}).strict();

export const evaluationSummarySchema = z.object({
  executionSuccessRate: z.number(),
  answerModeAccuracy: z.number().nullable(),
  expectedFactRecall: z.number().nullable(),
  prohibitedFactRate: z.number().nullable(),
  sourceRecallAtK: z.number().nullable(),
  citationComplianceRate: z.number().nullable(),
  versionAccuracy: z.number().nullable(),
  casePassRate: z.number(),
  latencyP50Ms: z.number().nonnegative(),
  latencyP95Ms: z.number().nonnegative(),
}).strict();

export const evaluationRunSchema = z.object({
  id: z.string(),
  datasetId: z.string(),
  agentKey: z.string(),
  agentVersionId: z.string(),
  ragPolicyVersionId: z.string(),
  knowledgeBindings: z.array(z.object({ knowledgeBaseId: z.string(), indexReleaseId: z.string() }).strict()),
  status: z.enum(['PENDING', 'RUNNING', 'SUCCEEDED', 'PARTIAL_FAILED', 'FAILED']),
  totalCount: z.number().int().nonnegative(),
  passedCount: z.number().int().nonnegative(),
  failedCount: z.number().int().nonnegative(),
  metrics: evaluationSummarySchema.nullable(),
  failureCode: z.string().nullable(),
  failureMessage: z.string().nullable(),
  createdAt: z.string(),
  startedAt: z.string().nullable(),
  finishedAt: z.string().nullable(),
}).strict();

const citationSchema = z.object({
  citation_no: z.number().int().positive(),
  knowledge_base_id: z.string(),
  document_id: z.string(),
  document_version_id: z.string(),
  index_release_id: z.string(),
  chunk_id: z.string(),
  document_title: z.string(),
  version_no: z.number().int().positive(),
  section_path: z.string().nullable(),
  page_no: z.number().int().positive().nullable(),
  quoted_text: z.string(),
  content_hash: z.string(),
  parent_id: z.string().nullable(),
  citation_type: z.enum(['FULL_PARENT', 'EXTRACTED_SPANS']).nullable(),
  original_spans: z.array(z.object({
    start_offset: z.number().int().nonnegative(),
    end_offset: z.number().int().positive(),
    content_hash: z.string(),
  }).strict()).nullable(),
}).strict();

export const evaluationCaseMetricsSchema = z.object({
  passed: z.boolean(),
  answerModeMatched: z.boolean(),
  expectedFactRecall: z.number().nullable(),
  prohibitedFactMatched: z.boolean().nullable(),
  sourceRecall: z.number().nullable(),
  citationCompliant: z.boolean().nullable(),
  versionMatched: z.boolean().nullable(),
  failures: z.array(z.string()),
}).strict();

export const evaluationCaseResultSchema = z.object({
  id: z.string(),
  runId: z.string(),
  caseId: z.string(),
  debugRunId: z.string().nullable(),
  executionStatus: z.enum(['SUCCEEDED', 'FAILED']),
  passed: z.boolean(),
  latencyMs: z.number().nonnegative(),
  answerMode: z.string().nullable(),
  answerMarkdown: z.string().nullable(),
  citations: z.array(citationSchema),
  metrics: evaluationCaseMetricsSchema.nullable(),
  errorCode: z.string().nullable(),
  errorMessage: z.string().nullable(),
  createdAt: z.string(),
}).strict();

export const evaluationDatasetDetailSchema = z.object({
  dataset: evaluationDatasetSchema,
  cases: z.array(evaluationCaseSchema),
  runs: z.array(evaluationRunSchema),
}).strict();

export const evaluationRunDetailSchema = z.object({
  run: evaluationRunSchema,
  cases: z.array(evaluationCaseSchema),
  results: z.array(evaluationCaseResultSchema),
}).strict();

export const evaluationImportResultSchema = z.object({
  createdCount: z.number().int().nonnegative(),
  updatedCount: z.number().int().nonnegative(),
  totalCount: z.number().int().nonnegative(),
}).strict();

export const evaluationRunComparisonSchema = z.object({
  baseline: evaluationRunSchema,
  candidate: evaluationRunSchema,
  metricDeltas: z.record(z.string(), z.number()),
  caseChanges: z.array(z.object({
    caseId: z.string(),
    baselinePassed: z.boolean().nullable(),
    candidatePassed: z.boolean(),
    change: z.enum(['NEW', 'UNCHANGED', 'IMPROVED', 'REGRESSED']),
  }).strict()),
}).strict();

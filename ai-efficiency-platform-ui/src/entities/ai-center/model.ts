import { z } from 'zod';
import {
  agentDefinitionSchema,
  agentDetailSchema,
  agentReleaseSchema,
  debugViewSchema,
  feedbackSchema,
  modelPolicySchema,
  promptDefinitionSchema,
  promptDetailSchema,
  ragPolicySchema,
  replaySchema,
  runSchema,
} from './schemas';
import {
  evaluationCaseResultSchema,
  evaluationCaseSchema,
  evaluationDatasetDetailSchema,
  evaluationDatasetSchema,
  evaluationRunComparisonSchema,
  evaluationRunDetailSchema,
  evaluationRunSchema,
} from './evaluationSchemas';

export type AgentDefinition = z.infer<typeof agentDefinitionSchema>;
export type AgentDetail = z.infer<typeof agentDetailSchema>;
export type AgentRelease = z.infer<typeof agentReleaseSchema>;
export type PromptDefinition = z.infer<typeof promptDefinitionSchema>;
export type PromptDetail = z.infer<typeof promptDetailSchema>;
export type ModelPolicy = z.infer<typeof modelPolicySchema>;
export type RagPolicy = z.infer<typeof ragPolicySchema>;
export type DebugView = z.infer<typeof debugViewSchema>;
export type AiRun = z.infer<typeof runSchema>;
export type AiFeedback = z.infer<typeof feedbackSchema>;
export type RunReplay = z.infer<typeof replaySchema>;
export type EvaluationDataset = z.infer<typeof evaluationDatasetSchema>;
export type EvaluationCase = z.infer<typeof evaluationCaseSchema>;
export type EvaluationRun = z.infer<typeof evaluationRunSchema>;
export type EvaluationCaseResult = z.infer<typeof evaluationCaseResultSchema>;
export type EvaluationDatasetDetail = z.infer<typeof evaluationDatasetDetailSchema>;
export type EvaluationRunDetail = z.infer<typeof evaluationRunDetailSchema>;
export type EvaluationRunComparison = z.infer<typeof evaluationRunComparisonSchema>;

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

import { z } from 'zod';
import { parseDeliverableSet as parseOperationDeliverableSet } from '../../entities/operation-deliverable';
export {
  type DeliverableSetDto,
  type DeliverableSetV1,
} from '../../entities/operation-deliverable';
import type { DeliverableSetDto } from '../../entities/operation-deliverable';

export type RunDisplayStatus =
  | 'queued'
  | 'running'
  | 'waiting_input'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'degraded_succeeded';
export type OperationChatStatus =
  | 'idle'
  | 'submitting'
  | 'streaming'
  | 'waiting_input'
  | 'cancelling'
  | 'succeeded'
  | 'degraded_succeeded'
  | 'failed'
  | 'cancelled';

export interface ConversationSubmitInput {
  message: string;
  requestId: string;
  userId: string;
  attachments?: Array<Record<string, unknown>>;
}
export interface ConversationSubmitViewV1 {
  contract_version: 'conversation/1';
  conversation_id: string;
  turn_id: string;
  run_id: string;
  status: 'queued';
}

export type StreamEventName =
  | 'run_started'
  | 'intent_detected'
  | 'clarification_required'
  | 'phase_started'
  | 'research_started'
  | 'research_completed'
  | 'content_generation_started'
  | 'content_generation_completed'
  | 'quality_checked'
  | 'assistant_started'
  | 'assistant_delta'
  | 'deliverable'
  | 'usage_update'
  | 'stream_error'
  | 'stream_done';
export interface StreamEventV1 {
  id: string;
  event: StreamEventName;
  contract_version: 'run.stream.event/1';
  run_id: string;
  sequence: number;
  payload: Record<string, unknown>;
}

export const conversationSubmitViewSchema = z.object({
  contract_version: z.literal('conversation/1'),
  conversation_id: z.string().min(1),
  turn_id: z.string().min(1),
  run_id: z.string().min(1),
  status: z.literal('queued'),
});

export type OperationVisiblePhase =
  | 'understanding_request'
  | 'collecting_sources'
  | 'checking_evidence'
  | 'creating_content'
  | 'checking_delivery';

export interface OperationPhaseProgress {
  completed: number;
  target: number;
}

export interface VisibleOperationPhase {
  phase: OperationVisiblePhase;
  label: string;
  completed?: number;
  target?: number;
}

export function parseDeliverableSet(value: unknown): DeliverableSetDto | null {
  return parseOperationDeliverableSet(value);
}

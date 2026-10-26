import { z } from 'zod';
import {
  answerModeSchema,
  citationSchema,
  conversationSchema,
  customerServiceSseSchema,
  feedbackSchema,
  messageViewSchema,
  publicProgressSchema,
  runSchema,
  submitSchema,
  timelineSchema,
} from './schemas';

export type AnswerMode = z.infer<typeof answerModeSchema>;
export type Conversation = z.infer<typeof conversationSchema>;
export type Citation = z.infer<typeof citationSchema>;
export type MessageView = z.infer<typeof messageViewSchema>;
export type CustomerServiceRun = z.infer<typeof runSchema>;
export type SubmitResult = z.infer<typeof submitSchema>;
export type Feedback = z.infer<typeof feedbackSchema>;
export type CustomerServiceSseEvent = z.infer<typeof customerServiceSseSchema>;
export type PublicProgress = z.infer<typeof publicProgressSchema>;
export type Timeline = z.infer<typeof timelineSchema>;

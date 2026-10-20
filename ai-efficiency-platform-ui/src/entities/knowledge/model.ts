import { z } from 'zod';
import {
  directorySchema,
  documentSchema,
  documentVersionSchema,
  indexReleaseSchema,
  ingestBatchSchema,
  knowledgeBaseSchema,
  processingTaskSchema,
} from './schemas';

export type KnowledgeBase = z.infer<typeof knowledgeBaseSchema>;
export type KnowledgeDirectory = z.infer<typeof directorySchema>;
export type KnowledgeDocument = z.infer<typeof documentSchema>;
export type DocumentVersion = z.infer<typeof documentVersionSchema>;
export type ProcessingTask = z.infer<typeof processingTaskSchema>;
export type IndexRelease = z.infer<typeof indexReleaseSchema>;
export type IngestBatch = z.infer<typeof ingestBatchSchema>;
export interface Page<T> {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
}

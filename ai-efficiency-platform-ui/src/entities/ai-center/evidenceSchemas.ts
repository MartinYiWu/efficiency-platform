import { z } from 'zod';

const modelPolicy = z
  .object({
    policy_key: z.string(),
    semantic_version: z.string(),
    provider: z.string(),
    model_name: z.string(),
    temperature: z.number(),
    top_p: z.number(),
    max_input_tokens: z.number(),
    max_output_tokens: z.number(),
    connect_timeout_ms: z.number(),
    read_timeout_ms: z.number(),
    max_retries: z.number(),
    checksum: z.string(),
  })
  .strict();
export const spanSchema = z
  .object({
    start_offset: z.number().int(),
    end_offset: z.number().int(),
    content_hash: z.string(),
  })
  .strict();

export const groupSchema = z
  .object({
    parent_ids: z.array(z.string()),
  })
  .strict();

export const exclusionSchema = z
  .object({
    parent_id: z.string().nullish(),
    reason: z.string(),
  })
  .strict();

export const budgetSchema = z
  .object({
    context_token_limit: z.number().int(),
    reserved_tokens: z.number().int(),
    used_tokens: z.number().int(),
    output_tokens: z.number().int(),
    safety_tokens: z.number().int(),
    fixed_input_tokens: z.number().int(),
    intermediate_output_tokens: z.number().int(),
    evidence_tokens: z.number().int(),
  })
  .strict();

export const extractionDecisionSchema = z
  .object({
    parent_id: z.string().nullish(),
    selected_sentence_ids: z.array(z.number().int()),
    reason: z.string(),
  })
  .strict();

export const conflictPairSchema = z
  .object({
    left_parent_id: z.string(),
    right_parent_id: z.string(),
    same_scope: z.boolean(),
    verdict: z.string(),
    left_quote: z.string(),
    right_quote: z.string(),
    reason: z.string(),
  })
  .strict();

export const conflictScreenSchema = z
  .object({
    pairs: z.array(conflictPairSchema),
    errors: z.array(z.string()),
    blocked: z.boolean(),
  })
  .strict();

export const parentSchema = z
  .object({
    parent_no: z.number().int().nullish(),
    source_table_id: z.number().int().nullish(),
    block_kind: z.string(),
    evidence_mode: z.string(),
    parent_id: z.string().nullish(),
    knowledge_base_id: z.string(),
    document_id: z.string(),
    document_version_id: z.string(),
    index_release_id: z.string(),
    document_title: z.string(),
    version_no: z.number().int(),
    section_path: z.string().nullish(),
    page_no: z.number().int().nullish(),
    page_end: z.number().int().nullish(),
    content: z.string(),
    content_hash: z.string(),
    token_count: z.number().int(),
  })
  .strict();

export const evidenceSchema = z
  .object({
    rank: z.number().int().nullish(),
    query_index: z.number().int().nullish(),
    chunk_id: z.string(),
    parent_id: z.string().nullish(),
    knowledge_base_id: z.string(),
    document_id: z.string(),
    document_version_id: z.string(),
    index_release_id: z.string(),
    document_title: z.string(),
    version_no: z.number().int(),
    section_path: z.string().nullish(),
    page_no: z.number().int().nullish(),
    content: z.string(),
    content_hash: z.string(),
    hit_content: z.string().nullish(),
    hit_content_hash: z.string().nullish(),
    hit_start_offset: z.number().int().nullish(),
    hit_end_offset: z.number().int().nullish(),
    score: z.number(),
  })
  .strict();

export const equivalenceResultSchema = z
  .object({
    left_chunk_id: z.string(),
    right_chunk_id: z.string(),
    verdict: z.string(),
    left_quote: z.string(),
    right_quote: z.string(),
    differing_conditions: z.array(z.string()),
  })
  .strict();

export const equivalenceDecisionSchema = z
  .object({
    left: evidenceSchema,
    right: evidenceSchema,
    left_parent: parentSchema,
    right_parent: parentSchema,
    similarity: z.number(),
    reason: z.string(),
    result: equivalenceResultSchema.nullish(),
    retained_parent_id: z.string().nullish(),
    merged_chunk_ids: z.array(z.string()),
  })
  .strict();

export const entrySchema = z
  .object({
    rank: z.number().int().nullish(),
    query_index: z.number().int().nullish(),
    chunk_id: z.string(),
    parent_id: z.string().nullish(),
    knowledge_base_id: z.string(),
    document_id: z.string(),
    document_version_id: z.string(),
    index_release_id: z.string(),
    document_title: z.string(),
    version_no: z.number().int(),
    section_path: z.string().nullish(),
    page_no: z.number().int().nullish(),
    content: z.string(),
    content_hash: z.string(),
    hit_content: z.string().nullish(),
    hit_content_hash: z.string().nullish(),
    hit_start_offset: z.number().int().nullish(),
    hit_end_offset: z.number().int().nullish(),
    score: z.number(),
    original_parent: parentSchema,
    citation_type: z.enum(['FULL_PARENT', 'EXTRACTED_SPANS']),
    original_spans: z.array(spanSchema),
    hit_chunk_ids: z.array(z.string()),
  })
  .strict();

export const packSchema = z
  .object({
    entries: z.array(entrySchema),
    groups: z.array(groupSchema),
    exclusions: z.array(exclusionSchema),
    model_policy: modelPolicy,
    budget: budgetSchema,
    blocked: z.boolean(),
    block_reasons: z.array(z.string()),
    extraction_decisions: z.array(extractionDecisionSchema),
    conflict_screen: conflictScreenSchema.nullish(),
  })
  .strict();

export const versionExclusionSchema = z
  .object({
    rank: z.number().int().nullish(),
    query_index: z.number().int().nullish(),
    chunk_id: z.string(),
    parent_id: z.string().nullish(),
    knowledge_base_id: z.string(),
    document_id: z.string(),
    document_version_id: z.string(),
    index_release_id: z.string(),
    score: z.number(),
    excerpt: z.string(),
    reason: z.string(),
  })
  .strict();

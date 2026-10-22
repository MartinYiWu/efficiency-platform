import { describe, expect, it } from 'vitest';

import { debugViewSchema, parseRetrievalFacts, runStepSchema } from './schemas';

describe('debugViewSchema', () => {
  it('accepts parent-child evidence and remains compatible with old debug records', () => {
    const baseline = {
      contract_version: 'customer-service-rag-debug-view/1',
      debug_run_id: 'run-1',
      status: 'SUCCEEDED',
      stages: [],
      answer_mode: null,
      answer_markdown: null,
      error_code: null,
      error_message: null,
    };
    expect(debugViewSchema.parse(baseline).parent_evidence).toEqual([]);
    expect(
      debugViewSchema.parse({
        ...baseline,
        vector_candidates: null,
        fts_candidates: null,
        fused_candidates: null,
        child_hits: null,
        parent_evidence: null,
        assembly_decisions: null,
      }).parent_evidence,
    ).toEqual([]);
    const result = debugViewSchema.parse({
      ...baseline,
      child_hits: [
        {
          chunk_id: 'child-1',
          parent_id: 'parent-1',
          document_version_id: 'version-1',
          index_release_id: 'index-1',
          score: 0.91,
          excerpt: '例外',
        },
      ],
      parent_evidence: [
        {
          parent_id: 'parent-1',
          document_version_id: 'version-1',
          index_release_id: 'index-1',
          document_title: '制度',
          version_no: 2,
          section_path: '请假',
          content: '完整条款',
          hit_chunk_ids: ['child-1'],
        },
      ],
      assembly_decisions: [{ parent_id: 'parent-1', selected: true, reason: 'SELECTED' }],
      budget_usage: { context_token_limit: 8000, used_tokens: 4500 },
      sufficiency: null,
    });
    expect(result.parent_evidence[0].content).toBe('完整条款');
    expect(result.child_hits[0].parent_id).toBe('parent-1');
  });
});

describe('parseRetrievalFacts', () => {
  it('reads projected retrieval facts and safely skips old run steps', () => {
    expect(parseRetrievalFacts('{"stage":"retrieval"}')).toBeNull();
    const facts = parseRetrievalFacts(
      JSON.stringify({
        retrieval_facts: {
          child_hits: [],
          parent_evidence: [
            {
              parent_id: 'parent-1',
              document_version_id: 'version-1',
              index_release_id: 'index-1',
              document_title: '制度',
              version_no: 2,
              section_path: null,
              content: '完整条款',
              hit_chunk_ids: ['child-1'],
            },
          ],
          assembly_decisions: [],
          budget_usage: null,
          sufficiency: null,
        },
      }),
    );
    expect(facts?.parent_evidence[0].content).toBe('完整条款');
  });
});

describe('runStepSchema', () => {
  it('accepts an answer delta event without a public summary', () => {
    const parsed = runStepSchema.parse({
      id: 'step-1',
      runId: 'run-1',
      sequenceNo: 6,
      stage: 'answer.delta',
      status: 'RUNNING',
      publicSummary: null,
      internalPayload: '{}',
      startedAt: '2026-10-22T03:20:15Z',
      finishedAt: '2026-10-22T03:20:15Z',
    });
    expect(parsed.publicSummary).toBeNull();
  });
});

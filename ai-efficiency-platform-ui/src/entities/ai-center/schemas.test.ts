import { describe, expect, it } from 'vitest';

import { debugViewSchema, parseRetrievalFacts, runStepSchema } from './schemas';

it('preserves helpful sufficiency decisions and still rejects unregistered fields', () => {
  const input = {
    contract_version: 'customer-service-rag-debug-view/1',
    debug_run_id: 'helpful-run',
    status: 'SUCCEEDED',
    stages: [],
    answer_mode: 'GENERAL_ADVICE',
    answer_markdown: '通用参考',
    error_code: null,
    error_message: null,
    sufficiency: {
      sufficient: false,
      supported_claims: [],
      unsupported_claims: ['报销流程'],
      conflicts: [],
      recommended_mode: 'GENERAL_ADVICE',
      evidence_status: 'NO_RELEVANT_EVIDENCE',
      general_advice_allowed: true,
      general_advice_scope: ['材料整理'],
      company_specific_unknowns: ['公司审批人'],
    },
  };
  const result = debugViewSchema.parse(input);
  expect(result.sufficiency?.general_advice_scope).toEqual(['材料整理']);
  expect(result.sufficiency?.company_specific_unknowns).toEqual(['公司审批人']);
  expect(() =>
    debugViewSchema.parse({ ...input, sufficiency: { ...input.sufficiency, unregistered: true } }),
  ).toThrow();
});

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
      citations: [
        {
          citation_no: 1,
          knowledge_base_id: 'kb',
          document_id: 'doc',
          document_version_id: 'version-1',
          index_release_id: 'index-1',
          chunk_id: 'child-1',
          document_title: '制度',
          version_no: 2,
          section_path: '请假',
          page_no: 1,
          quoted_text: '完整条款',
          content_hash: 'hash',
          parent_id: 'parent-1',
          citation_type: 'FULL_PARENT',
          original_spans: [{ start_offset: 0, end_offset: 4, content_hash: 'span-hash' }],
        },
      ],
    });
    expect(result.parent_evidence[0].content).toBe('完整条款');
    expect(result.child_hits[0].parent_id).toBe('parent-1');
    expect(result.citations[0].document_title).toBe('制度');
    expect(debugViewSchema.parse(baseline).citations).toEqual([]);
  });
});

describe('parseRetrievalFacts', () => {
  it('preserves recorded zero scores, exclusions and conflicts while leaving old facts absent', () => {
    const candidate = {
      chunk_id: 'c',
      parent_id: 'p',
      document_version_id: 'v',
      index_release_id: 'i',
      knowledge_base_id: 'kb',
      document_id: 'd',
      rank: 1,
      query_index: 1,
      score: 0,
      excerpt: '原文',
    };
    const facts = parseRetrievalFacts(
      JSON.stringify({
        retrieval_facts: {
          child_hits: [candidate],
          equivalence_decisions: [],
          equivalence_errors: [],
          version_exclusions: [{ ...candidate, reason: 'NOT_BOUND_INDEX_MEMBER' }],
          final_parent_candidates: ['p'],
          evidence_groups: [{ parent_ids: ['p', 'p2'] }],
          grouping_decisions: [{ parent_id: 'p', reason: 'ADJACENT' }],
          conflict_screen: {
            pairs: [
              {
                left_parent_id: 'p',
                right_parent_id: 'p2',
                same_scope: true,
                verdict: 'CONFLICT',
                left_quote: '允许',
                right_quote: '禁止',
                reason: '同条件相反',
              },
            ],
            errors: [],
            blocked: true,
          },
        },
      }),
    );
    expect(facts).not.toBeNull();
    expect(facts).toMatchObject({
      child_hits: [{ score: 0, rank: 1 }],
      conflict_screen: { blocked: true },
    });
    expect(parseRetrievalFacts('{"retrieval_facts":{}}')).not.toHaveProperty('evidence_pack', {});
  });

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

import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { parseRetrievalFacts } from '../../entities/ai-center/schemas';
import { EvidenceFactsPanel } from './EvidenceFactsPanel';

it('renders frozen zero budget, exact conflicts, exclusion reasons and selected model', () => {
  const facts = parseRetrievalFacts(
    JSON.stringify({
      retrieval_facts: {
        equivalence_decisions: [],
        equivalence_errors: [],
        version_exclusions: [],
        evidence_groups: [{ parent_ids: ['p1', 'p2'] }],
        final_parent_candidates: ['p1', 'p2'],
        grouping_decisions: [],
        conflict_screen: {
          pairs: [
            {
              left_parent_id: 'p1',
              right_parent_id: 'p2',
              same_scope: true,
              verdict: 'CONFLICT',
              left_quote: '允许远程',
              right_quote: '禁止远程',
              reason: '同一适用范围',
            },
          ],
          errors: [],
          blocked: true,
        },
        evidence_pack: {
          entries: [],
          groups: [],
          exclusions: [{ parent_id: 'p1', reason: 'BUDGET_EXCLUDED' }],
          model_policy: {
            policy_key: 'large',
            semantic_version: '1',
            provider: 'fake',
            model_name: 'frozen-model',
            temperature: 0,
            top_p: 1,
            max_input_tokens: 64000,
            max_output_tokens: 1000,
            connect_timeout_ms: 10,
            read_timeout_ms: 10,
            max_retries: 0,
            checksum: 'hash',
          },
          budget: {
            context_token_limit: 100,
            used_tokens: 0,
            reserved_tokens: 100,
            fixed_input_tokens: 70,
            evidence_tokens: 0,
            output_tokens: 10,
            safety_tokens: 20,
            intermediate_output_tokens: 0,
          },
          blocked: true,
          block_reasons: ['CONFLICT'],
          extraction_decisions: [],
          conflict_screen: null,
        },
      },
    }),
  );
  expect(facts).not.toBeNull();
  if (!facts) throw new Error('fixture contract mismatch');
  render(<EvidenceFactsPanel facts={facts} />);
  expect(screen.getByText('frozen-model')).toBeInTheDocument();
  expect(screen.getByText('允许远程')).toBeInTheDocument();
  expect(screen.getByText('禁止远程')).toBeInTheDocument();
  expect(screen.getByText('BUDGET_EXCLUDED')).toBeInTheDocument();
  expect(screen.getByText('旧版过滤计数：0')).toBeInTheDocument();
  expect(screen.getByText(/相邻组成员：p1 → p2/)).toBeInTheDocument();
});

import { expect, it } from 'vitest';
import {
  conflictPairSchema,
  equivalenceResultSchema,
  exclusionSchema,
  extractionDecisionSchema,
  parentSchema,
  spanSchema,
} from './evidenceSchemas';
import { parseRetrievalFacts } from './schemas';

it.each([
  [-1, 3],
  [3, 3],
  [4, 3],
])('rejects invalid span [%s,%s)', (start_offset, end_offset) => {
  expect(spanSchema.safeParse({ start_offset, end_offset, content_hash: 'hash' }).success).toBe(
    false,
  );
});
it('accepts a zero-based span and legacy missing facts', () => {
  expect(
    spanSchema.safeParse({ start_offset: 0, end_offset: 3, content_hash: 'hash' }).success,
  ).toBe(true);
  expect(parseRetrievalFacts('{"retrieval_facts":{}}')).not.toBeNull();
});
it('rejects invalid frozen enums and missing required parent identities', () => {
  expect(conflictPairSchema.shape.verdict.safeParse('INVALID').success).toBe(false);
  expect(equivalenceResultSchema.shape.verdict.safeParse('INVALID').success).toBe(false);
  expect(parentSchema.shape.block_kind.safeParse('INVALID').success).toBe(false);
  expect(parentSchema.shape.evidence_mode.safeParse('INVALID').success).toBe(false);
  for (const schema of [parentSchema, exclusionSchema, extractionDecisionSchema]) {
    for (const invalid of [undefined, null, ''])
      expect(schema.shape.parent_id.safeParse(invalid).success).toBe(false);
  }
});

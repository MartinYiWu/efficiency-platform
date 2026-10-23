import { fireEvent, render, screen, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { citationSchema } from '../../entities/customer-service/schemas';
import { CitationDrawer } from './CitationDrawer';

const citation = citationSchema.parse({
  id: 'c',
  runId: 'r',
  messageId: 'm',
  citationNo: 1,
  knowledgeBaseId: 'k',
  documentId: 'd',
  documentVersionId: 'v',
  indexReleaseId: 'i',
  chunkId: 'ch',
  documentTitle: '技术指南',
  versionNo: 1,
  sectionPath: null,
  pageNo: null,
  quotedText: '准确原文',
  contentHash: 'hash',
  createdAt: 'now',
  parentId: 'p',
  citationType: 'EXTRACTED_SPANS',
  originalSpans: [
    { start_offset: 0, end_offset: 4, content_hash: 'hash' },
    { start_offset: 10, end_offset: 15, content_hash: 'hash2' },
  ],
});

it('shows excerpt identity and every offset in the closable public drawer', () => {
  const onClose = vi.fn();
  render(<CitationDrawer citation={citation} onClose={onClose} />);
  const dialog = within(screen.getByRole('dialog'));
  expect(dialog.getByText('原文节选')).toBeInTheDocument();
  expect(dialog.getByText('[0, 4)')).toBeInTheDocument();
  expect(dialog.getByText('[10, 15)')).toBeInTheDocument();
  expect(dialog.queryByText(/score|Prompt|CONFLICT|hash2/)).not.toBeInTheDocument();
  fireEvent.click(dialog.getByRole('button', { name: 'Close' }));
  expect(onClose).toHaveBeenCalledOnce();
});
it.each([
  ['FULL_PARENT', '完整原文'],
  [null, '该版本未记录'],
] as const)('distinguishes %s from unrecorded history', (citationType, label) => {
  render(
    <CitationDrawer
      citation={{ ...citation, citationType, originalSpans: null }}
      onClose={() => {}}
    />,
  );
  expect(within(screen.getByRole('dialog')).getAllByText(label).length).toBeGreaterThan(0);
});

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
  sectionPath: '/ 开发流程',
  pageNo: null,
  quotedText: '- **关键要求**：完成自测后提交。',
  contentHash: 'hash',
  createdAt: 'now',
  parentId: 'p',
  citationType: 'EXTRACTED_SPANS',
  originalSpans: [
    { start_offset: 0, end_offset: 4, content_hash: 'hash' },
    { start_offset: 10, end_offset: 15, content_hash: 'hash2' },
  ],
});

it('shows a readable excerpt and closes without exposing internal offsets', async () => {
  const onClose = vi.fn();
  render(<CitationDrawer citation={citation} onClose={onClose} />);
  const dialog = within(screen.getByRole('dialog'));
  expect(dialog.getByText('技术指南')).toBeInTheDocument();
  expect(dialog.getByText('原文节选')).toBeInTheDocument();
  expect(await dialog.findByText('关键要求')).toHaveProperty('tagName', 'STRONG');
  expect(dialog.queryByText(/原文偏移|hash2|\[0, 4\)/)).not.toBeInTheDocument();
  fireEvent.click(dialog.getByRole('button', { name: 'Close' }));
  expect(onClose).toHaveBeenCalledOnce();
});

it('distinguishes a full source from an excerpt', () => {
  render(<CitationDrawer citation={{ ...citation, citationType: 'FULL_PARENT', originalSpans: null }} onClose={() => {}} />);
  expect(within(screen.getByRole('dialog')).getByText('完整原文')).toBeInTheDocument();
});

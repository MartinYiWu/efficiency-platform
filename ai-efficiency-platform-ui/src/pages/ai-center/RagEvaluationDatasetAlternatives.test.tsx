import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';

import * as api from '../../features/ai-center/api';
import { RagEvaluationDatasetPage } from './RagEvaluationDatasetPage';

afterEach(() => vi.restoreAllMocks());

it.each([
  ['原事实', { 原事实: ['完整等价表述'] }],
  ['', {}],
  ['新语义事实', {}],
])('keeps only alternatives whose original fact remains: %s', async (facts, alternatives) => {
  const expectedFactAlternatives = { 原事实: ['完整等价表述'] };
  vi.spyOn(api, 'getEvaluationDataset').mockResolvedValue({
    dataset: {
      id: 'd',
      name: '评测集',
      description: null,
      agentKey: 'customer-service',
      status: 'ACTIVE',
      caseCount: 1,
      createdAt: 'now',
      updatedAt: 'now',
    },
    cases: [
      {
        id: 'c',
        datasetId: 'd',
        caseNo: '1',
        question: '问题',
        expectedAnswerMode: 'COMPANY_KNOWLEDGE',
        expectedFacts: ['原事实'],
        expectedFactAlternatives,
        prohibitedFacts: [],
        expectedDocumentTitles: [],
        expectedDocumentVersionIds: [],
        minCitationCount: 0,
        tags: [],
        enabled: true,
      },
    ],
    runs: [],
  });
  const update = vi
    .spyOn(api, 'updateEvaluationCase')
    .mockImplementation(async () => (await api.getEvaluationDataset('')).cases[0]);
  render(
    <MemoryRouter>
      <RagEvaluationDatasetPage />
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole('button', { name: '编辑' }));
  const dialog = within(screen.getByRole('dialog'));
  expect(dialog.getByText(/删除或改名事实后，原绑定会在保存时移除/)).toBeInTheDocument();
  fireEvent.change(dialog.getByLabelText('真实提问'), { target: { value: '修改后的问题' } });
  fireEvent.change(dialog.getByLabelText('必须事实（每行一条）'), { target: { value: facts } });
  fireEvent.click(dialog.getByRole('button', { name: /保\s*存/ }));
  await waitFor(() =>
    expect(update).toHaveBeenCalledWith(
      '',
      'c',
      expect.objectContaining({
        question: '修改后的问题',
        expectedFactAlternatives: alternatives,
      }),
    ),
  );
});

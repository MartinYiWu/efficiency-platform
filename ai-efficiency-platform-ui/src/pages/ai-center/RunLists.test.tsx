import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';

import * as api from '../../features/ai-center/api';
import { RunListPage } from './RunListPage';
import { FeedbackPage } from './FeedbackPage';

afterEach(() => vi.restoreAllMocks());

it('loads a requested run page from the real paged contract', async () => {
  const list = vi
    .spyOn(api, 'listRuns')
    .mockResolvedValue({ items: [], page: 1, pageSize: 10, total: 25 });
  render(
    <MemoryRouter>
      <RunListPage />
    </MemoryRouter>,
  );
  await waitFor(() => expect(list).toHaveBeenCalled());
  fireEvent.click(await screen.findByTitle('2'));
  await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.stringContaining('page=2')));
});

it('preserves the reason filter when paging through feedback', async () => {
  const list = vi
    .spyOn(api, 'listFeedback')
    .mockResolvedValue({ items: [], page: 1, pageSize: 10, total: 25 });
  render(
    <MemoryRouter>
      <FeedbackPage />
    </MemoryRouter>,
  );
  await waitFor(() => expect(list).toHaveBeenCalled());
  fireEvent.change(screen.getByPlaceholderText('原因编码'), { target: { value: 'INCORRECT' } });
  fireEvent.click(screen.getByRole('button', { name: '查 询' }));
  await waitFor(() =>
    expect(list).toHaveBeenLastCalledWith(expect.stringContaining('reasonCode=INCORRECT')),
  );
  fireEvent.click(await screen.findByTitle('2'));
  await waitFor(() => {
    expect(list).toHaveBeenLastCalledWith(expect.stringContaining('page=2'));
    expect(list).toHaveBeenLastCalledWith(expect.stringContaining('reasonCode=INCORRECT'));
  });
});

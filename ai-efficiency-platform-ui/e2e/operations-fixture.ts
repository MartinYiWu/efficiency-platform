import type { Page } from '@playwright/test';

export const envelope = (data: unknown) => ({ code: 'SUCCESS', message: '成功', data });

export const queuedRun = (conversationId: string, runId: string) => ({
  conversationId,
  runId,
  agentRunId: runId,
  status: 'queued',
  failureCode: null,
  failureMessage: null,
  lastEventSequence: 0,
});

export async function installOperationConversation(page: Page) {
  await page.route('**/api/operations/conversations', async (route) => {
    await route.fulfill({
      json: envelope({
        conversationId: 'conversation-fixture',
        title: null,
        status: 'active',
        createdAt: '2026-10-30T00:00:00Z',
      }),
    });
  });
  await page.route('**/api/operations/conversations/*/artifacts', async (route) => {
    const conversationId = new URL(route.request().url()).pathname.split('/').at(-2);
    await route.fulfill({ json: envelope({ conversationId, artifacts: [] }) });
  });
}

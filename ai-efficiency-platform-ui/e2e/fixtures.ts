import { expect, test as base } from '@playwright/test';
import { isIsolatedRequest } from './request-isolation';

export { expect };
export type { Page, Locator } from '@playwright/test';

export const test = base.extend<{ apiIsolation: void }>({
  apiIsolation: [
    async ({ context, baseURL }, use) => {
      const unhandled: string[] = [];
      await context.route('**/*', async (route) => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        if (isIsolatedRequest(request.url(), request.resourceType(), baseURL!)) {
          unhandled.push(`${request.method()} ${path}`);
          await route.abort('blockedbyclient');
          return;
        }
        await route.continue();
      });
      await use();
      expect(unhandled, '默认 E2E 禁止未被 fixture 拦截的 API 请求').toEqual([]);
    },
    { auto: true },
  ],
});

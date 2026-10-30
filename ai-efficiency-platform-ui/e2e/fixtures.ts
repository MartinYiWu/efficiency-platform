import { expect, test as base } from '@playwright/test';

export { expect };

export const test = base.extend<{ apiIsolation: void }>({
  apiIsolation: [
    async ({ context }, use) => {
      const unhandled: string[] = [];
      await context.route('**/*', async (route) => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        if (/^\/(api|v1)(\/|$)/.test(path) || ['fetch', 'xhr'].includes(request.resourceType())) {
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

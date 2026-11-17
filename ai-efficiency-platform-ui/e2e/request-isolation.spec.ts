import { expect, test } from '@playwright/test';
import { isIsolatedRequest } from './request-isolation';

test('默认浏览器夹具拒绝所有外源资源类型，不仅fetch', async () => {
  for (const type of ['script', 'image', 'font', 'document', 'eventsource', 'fetch', 'xhr']) {
    expect(
      isIsolatedRequest('https://external.invalid/probe', type, 'http://127.0.0.1:5190'),
      type,
    ).toBe(true);
  }
  expect(
    isIsolatedRequest('http://127.0.0.1:5190/assets/app.js', 'script', 'http://127.0.0.1:5190'),
  ).toBe(false);
  expect(
    isIsolatedRequest('http://127.0.0.1:5190/api/probe', 'eventsource', 'http://127.0.0.1:5190'),
  ).toBe(true);
});

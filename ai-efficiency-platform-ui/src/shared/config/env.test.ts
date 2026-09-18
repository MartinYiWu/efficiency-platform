import { describe, expect, it } from 'vitest';

import { getAppConfig } from './env';

describe('getAppConfig', () => {
  it('returns the configured API base URL', () => {
    expect(
      getAppConfig({
        VITE_API_BASE_URL: 'https://api.example.com',
      }),
    ).toEqual({
      apiBaseUrl: 'https://api.example.com',
    });
  });

  it('rejects a missing API base URL', () => {
    expect(() => getAppConfig({})).toThrow('VITE_API_BASE_URL must be a valid URL');
  });
});

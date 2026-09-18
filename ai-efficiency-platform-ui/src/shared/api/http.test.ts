import { describe, expect, it } from 'vitest';

import { createHttpClient } from './http';

describe('createHttpClient', () => {
  it('uses the supplied API base URL', () => {
    const client = createHttpClient('https://api.example.com');

    expect(client.defaults.baseURL).toBe('https://api.example.com');
  });
});

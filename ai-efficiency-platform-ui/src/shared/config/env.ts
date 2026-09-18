import { z } from 'zod';

const appConfigSchema = z.object({
  VITE_API_BASE_URL: z.string().url(),
});

export interface AppConfig {
  apiBaseUrl: string;
}

export function getAppConfig(env: Record<string, string | undefined>): AppConfig {
  const parsedConfig = appConfigSchema.safeParse(env);

  if (!parsedConfig.success) {
    throw new Error('VITE_API_BASE_URL must be a valid URL');
  }

  return {
    apiBaseUrl: parsedConfig.data.VITE_API_BASE_URL,
  };
}

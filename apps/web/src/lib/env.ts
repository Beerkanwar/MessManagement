/**
 * Environment configuration for the Web Application.
 * Only non-secret values exposed via VITE_ prefixes [SPEC SDD §7, ImplementationGuide Phase 15].
 */

export interface AppEnv {
  apiBasePath: string;
  appVersion: string;
  environmentName: string;
  isProduction: boolean;
}

export const env: AppEnv = {
  apiBasePath: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  appVersion: import.meta.env.VITE_APP_VERSION || '1.0.0',
  environmentName: import.meta.env.VITE_ENV_NAME || (import.meta.env.MODE === 'production' ? 'production' : 'development'),
  isProduction: import.meta.env.MODE === 'production',
};


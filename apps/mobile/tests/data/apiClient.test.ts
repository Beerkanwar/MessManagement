// Test Checkpoint: API client, concurrent 401 shared refresh, headers, in-memory access token, normalized errors
import { ApiClient } from '../../src/data/api/apiClient';
import { InMemorySecureStorage } from '../../src/data/storage/secureStorage';
import { AppError } from '../../src/domain/types';

describe('Data: ApiClient', () => {
  let storage: InMemorySecureStorage;
  let client: ApiClient;
  let originalFetch: typeof global.fetch;

  beforeEach(() => {
    storage = new InMemorySecureStorage();
    client = new ApiClient({
      baseUrl: 'http://test-server/api/v1',
      secureStorage: storage,
      appVersion: '1.2.3',
      platform: 'ANDROID',
    });
    originalFetch = global.fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('keeps access token in-memory only and never persists it to secure storage', async () => {
    client.setAccessToken('mem_token_abc123');
    expect(client.getAccessToken()).toBe('mem_token_abc123');

    // Secure storage must NOT contain the access token
    expect(await storage.getItemAsync('access_token')).toBeNull();
    expect(await storage.getItemAsync('mess_access_token')).toBeNull();
  });

  it('injects version, platform, device id and Bearer token headers into requests', async () => {
    client.setAccessToken('valid_jwt_token');
    await storage.setItemAsync('mess_device_unique_id', 'test-device-id-999');

    let capturedHeaders: Record<string, string> = {};

    global.fetch = jest.fn().mockImplementation(async (url: string, init?: RequestInit) => {
      capturedHeaders = (init?.headers as Record<string, string>) || {};
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => ({ status: 'ok' }),
      } as any;
    });

    await client.request('/test/endpoint');

    expect(capturedHeaders['X-App-Version']).toBe('1.2.3');
    expect(capturedHeaders['X-Platform']).toBe('ANDROID');
    expect(capturedHeaders['X-Device-Id']).toBe('test-device-id-999');
    expect(capturedHeaders['Authorization']).toBe('Bearer valid_jwt_token');
  });

  it('normalizes error responses to AppError instances with status and codes', async () => {
    global.fetch = jest.fn().mockImplementation(async () => {
      return {
        ok: false,
        status: 403,
        headers: { get: () => 'application/json' },
        json: async () => ({
          code: 'WRONG_CLIENT',
          message: 'Staff roles must sign in using the web application.',
        }),
      } as any;
    });

    await expect(client.request('/test/endpoint')).rejects.toThrow(AppError);

    try {
      await client.request('/test/endpoint');
    } catch (e: any) {
      expect(e).toBeInstanceOf(AppError);
      expect(e.code).toBe('WRONG_CLIENT');
      expect(e.status).toBe(403);
      expect(e.message).toContain('Staff roles');
    }
  });

  it('executes exactly one shared refresh call for concurrent 401s and retries', async () => {
    await storage.setItemAsync('mess_refresh_token', 'initial_refresh_token');
    client.setAccessToken('expired_access_token');

    let refreshCallCount = 0;
    let dataCallCount = 0;

    global.fetch = jest.fn().mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.includes('/auth/refresh')) {
        refreshCallCount++;
        return {
          ok: true,
          status: 200,
          headers: { get: () => 'application/json' },
          json: async () => ({
            access_token: 'new_refreshed_access_token',
            refresh_token: 'new_rotated_refresh_token',
          }),
        } as any;
      }

      dataCallCount++;
      const authHeader = (init?.headers as Record<string, string>)?.['Authorization'];

      // First time with expired token -> 401
      if (authHeader === 'Bearer expired_access_token') {
        return {
          ok: false,
          status: 401,
          headers: { get: () => 'application/json' },
          json: async () => ({ code: 'TOKEN_EXPIRED', message: 'Access token expired' }),
        } as any;
      }

      // After refresh with new token -> 200 OK
      if (authHeader === 'Bearer new_refreshed_access_token') {
        return {
          ok: true,
          status: 200,
          headers: { get: () => 'application/json' },
          json: async () => ({ data: 'success_data' }),
        } as any;
      }

      return { ok: false, status: 500, headers: { get: () => '' } } as any;
    });

    // Fire 3 concurrent requests that both encounter 401
    const [res1, res2, res3] = await Promise.all([
      client.request('/data/resource1'),
      client.request('/data/resource2'),
      client.request('/data/resource3'),
    ]);

    expect(res1).toEqual({ data: 'success_data' });
    expect(res2).toEqual({ data: 'success_data' });
    expect(res3).toEqual({ data: 'success_data' });

    // Shared refresh promise mutex ensures refresh was called ONLY ONCE
    expect(refreshCallCount).toBe(1);
    expect(client.getAccessToken()).toBe('new_refreshed_access_token');
    expect(await storage.getItemAsync('mess_refresh_token')).toBe('new_rotated_refresh_token');
  });

  it('triggers onDeviceReplaced callback when refresh response indicates device replacement', async () => {
    await storage.setItemAsync('mess_refresh_token', 'replaced_device_token');
    client.setAccessToken('old_token');

    let deviceReplacedTriggered = false;
    client.onDeviceReplaced = () => {
      deviceReplacedTriggered = true;
    };

    global.fetch = jest.fn().mockImplementation(async (url: string) => {
      if (url.includes('/auth/refresh')) {
        return {
          ok: false,
          status: 401,
          headers: { get: () => 'application/json' },
          json: async () => ({
            code: 'DEVICE_REPLACED',
            message: 'You signed in on another phone.',
          }),
        } as any;
      }
      return {
        ok: false,
        status: 401,
        headers: { get: () => 'application/json' },
        json: async () => ({ code: 'UNAUTHORIZED' }),
      } as any;
    });

    await expect(client.request('/protected/resource')).rejects.toThrow();
    expect(deviceReplacedTriggered).toBe(true);
    // Tokens must be cleared
    expect(client.getAccessToken()).toBeNull();
    expect(await storage.getItemAsync('mess_refresh_token')).toBeNull();
  });
});

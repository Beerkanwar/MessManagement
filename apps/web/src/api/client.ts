/**
 * API Client Layer [SPEC SDD §11, DEC-10, ImplementationGuide Phase 15].
 * - In-memory access token storage (never localStorage, sessionStorage, or visible logs)
 * - Shared refresh call on 401 deduplication (all concurrent requests queue behind single refresh)
 * - Normalized AppError envelope parsing
 * - Device replaced / revoked detection and global listener dispatch
 * - Idempotency: GET requests retry on network error; POST/PUT/DELETE never retry automatically
 */
import { env } from '../lib/env';
import { AppError, getErrorMessage } from './errors';

type DeviceReplacedListener = () => void;
type AuthFailureListener = () => void;

class ApiClient {
  private accessToken: string | null = null;
  private refreshPromise: Promise<string | null> | null = null;
  private deviceReplacedListeners: Set<DeviceReplacedListener> = new Set();
  private authFailureListeners: Set<AuthFailureListener> = new Set();

  public setAccessToken(token: string | null) {
    this.accessToken = token;
  }

  public getAccessToken(): string | null {
    return this.accessToken;
  }

  public onDeviceReplaced(listener: DeviceReplacedListener) {
    this.deviceReplacedListeners.add(listener);
    return () => this.deviceReplacedListeners.delete(listener);
  }

  public onAuthFailure(listener: AuthFailureListener) {
    this.authFailureListeners.add(listener);
    return () => this.authFailureListeners.delete(listener);
  }

  private notifyDeviceReplaced() {
    this.deviceReplacedListeners.forEach((fn) => fn());
  }

  private notifyAuthFailure() {
    this.authFailureListeners.forEach((fn) => fn());
  }

  /**
   * Refreshes the access token using the HttpOnly cookie (or in-memory credentials).
   * Ensures concurrent requests share exactly one in-flight promise.
   */
  public async refreshAccessToken(): Promise<string | null> {
    if (this.refreshPromise) {
      return this.refreshPromise;
    }

    this.refreshPromise = (async () => {
      try {
        const response = await fetch(`${env.apiBasePath}/auth/refresh`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          // credentials: 'include' passes the HttpOnly cookie scoped to auth
          credentials: 'include',
          body: JSON.stringify({}),
        });

        if (!response.ok) {
          const errData = await response.json().catch(() => ({}));
          const code = errData?.error?.code || errData?.code;
          if (code === 'DEVICE_REVOKED' || code === 'DEVICE_REPLACED') {
            this.notifyDeviceReplaced();
          } else {
            this.notifyAuthFailure();
          }
          this.setAccessToken(null);
          return null;
        }

        const data = await response.json();
        const newToken = data.access || data.tokens?.access;
        if (newToken) {
          this.setAccessToken(newToken);
          return newToken;
        }
        this.notifyAuthFailure();
        this.setAccessToken(null);
        return null;
      } catch {
        this.notifyAuthFailure();
        this.setAccessToken(null);
        return null;
      } finally {
        this.refreshPromise = null;
      }
    })();

    return this.refreshPromise;
  }

  /**
   * Main request method with 401 interceptor, error normalization, and safe retry rules.
   */
  public async request<T = any>(
    path: string,
    options: RequestInit = {},
    isRetry = false
  ): Promise<T> {
    const normalizedPath = path.startsWith('/api/v1') ? path.replace(/^\/api\/v1/, '') : path;
    const url = path.startsWith('http') ? path : `${env.apiBasePath}${normalizedPath.startsWith('/') ? normalizedPath : `/${normalizedPath}`}`;
    const method = (options.method || 'GET').toUpperCase();

    const headers = new Headers(options.headers || {});
    if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
      headers.set('Content-Type', 'application/json');
    }

    if (this.accessToken && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${this.accessToken}`);
    }

    let response: Response;
    try {
      response = await fetch(url, {
        ...options,
        method,
        headers,
        credentials: 'include',
      });
    } catch (networkErr: any) {
      // Retry once only for idempotent GET requests on network failure
      if (method === 'GET' && !isRetry) {
        return this.request<T>(path, options, true);
      }
      throw new AppError({
        code: 'NETWORK_ERROR',
        message: getErrorMessage('NETWORK_ERROR'),
        status: 0,
      });
    }

    // 401 Unauthorized interceptor: run single shared refresh and retry once
    if (response.status === 401 && !isRetry && !path.includes('/auth/login') && !path.includes('/auth/refresh')) {
      const refreshedToken = await this.refreshAccessToken();
      if (refreshedToken) {
        return this.request<T>(path, options, true);
      }
    }

    // Handle non-2xx responses
    if (!response.ok) {
      let errorBody: any = null;
      try {
        errorBody = await response.json();
      } catch {
        errorBody = null;
      }

      // Extract error details from standard envelope (Phase 1 / SDD §88)
      const errObj = errorBody?.error || errorBody || {};
      const code = errObj.code || `HTTP_${response.status}`;
      const message = errObj.message || getErrorMessage(code, response.statusText);
      const traceId = errObj.trace_id || response.headers.get('x-correlation-id') || undefined;
      const fieldErrors = errObj.details || undefined;

      // Detect single active device replacement
      if (code === 'DEVICE_REVOKED' || code === 'DEVICE_REPLACED') {
        this.notifyDeviceReplaced();
      }

      throw new AppError({
        code,
        message,
        status: response.status,
        traceId,
        fieldErrors,
      });
    }

    // Handle 204 No Content
    if (response.status === 204) {
      return {} as T;
    }

    return response.json();
  }

  public get<T>(path: string, options?: RequestInit): Promise<T> {
    return this.request<T>(path, { ...options, method: 'GET' });
  }

  public post<T>(path: string, body?: any, options?: RequestInit): Promise<T> {
    return this.request<T>(path, {
      ...options,
      method: 'POST',
      body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
    });
  }

  public put<T>(path: string, body?: any, options?: RequestInit): Promise<T> {
    return this.request<T>(path, {
      ...options,
      method: 'PUT',
      body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
    });
  }

  public patch<T>(path: string, body?: any, options?: RequestInit): Promise<T> {
    return this.request<T>(path, {
      ...options,
      method: 'PATCH',
      body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
    });
  }

  public delete<T>(path: string, options?: RequestInit): Promise<T> {
    return this.request<T>(path, { ...options, method: 'DELETE' });
  }
}

export const apiClient = new ApiClient();


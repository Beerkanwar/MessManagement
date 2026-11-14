// API Client with Normalized Errors, In-Memory Access Token, and Concurrent 401 Refresh Mutex
// per SDD §6.1, SDD §7, Build Item 4
import { AppError, User, UserRole, AssignmentSummary, DeviceSummary, VersionPolicy } from '../../domain/types';
import { ISecureStorage, defaultSecureStorage } from '../storage/secureStorage';
import { logger } from '../../platform/diagnostics';

const REFRESH_TOKEN_KEY = 'mess_refresh_token';
const DEVICE_ID_KEY = 'mess_device_unique_id';

export interface AuthMeResponse {
  user: User;
  role: UserRole;
  assignment: AssignmentSummary | null;
  device: DeviceSummary | null;
  version_policy: VersionPolicy;
}

export interface LoginResponse {
  user: User;
  role: UserRole;
  access_token: string;
  refresh_token: string;
  device_id: string;
  platform: string;
  session_status: string;
}

export interface ApiClientConfig {
  baseUrl?: string;
  secureStorage?: ISecureStorage;
  appVersion?: string;
  platform?: 'ANDROID' | 'IOS';
}

export class ApiClient {
  private baseUrl: string;
  private secureStorage: ISecureStorage;
  private appVersion: string;
  private platform: 'ANDROID' | 'IOS';

  // Access token is held STRICTLY in memory only (Build Item 4)
  private accessToken: string | null = null;
  private refreshPromise: Promise<string> | null = null;

  public onDeviceReplaced?: () => void;
  public onSessionExpired?: () => void;

  constructor(config: ApiClientConfig = {}) {
    this.baseUrl = config.baseUrl || process.env.EXPO_PUBLIC_API_URL || 'http://10.0.2.2:8000/api/v1';
    this.secureStorage = config.secureStorage || defaultSecureStorage;
    this.appVersion = config.appVersion || '1.0.0';
    this.platform = config.platform || 'ANDROID';
  }

  public setBaseUrl(url: string): void {
    this.baseUrl = url;
  }

  public setAppInfo(appVersion: string, platform: 'ANDROID' | 'IOS'): void {
    this.appVersion = appVersion;
    this.platform = platform;
  }

  public setSecureStorage(storage: ISecureStorage): void {
    this.secureStorage = storage;
  }

  public setAccessToken(token: string | null): void {
    this.accessToken = token;
  }

  public getAccessToken(): string | null {
    return this.accessToken;
  }

  public async getStoredRefreshToken(): Promise<string | null> {
    return await this.secureStorage.getItemAsync(REFRESH_TOKEN_KEY);
  }

  public async setStoredRefreshToken(token: string): Promise<void> {
    await this.secureStorage.setItemAsync(REFRESH_TOKEN_KEY, token);
  }

  public async clearStoredTokens(): Promise<void> {
    this.accessToken = null;
    await this.secureStorage.deleteItemAsync(REFRESH_TOKEN_KEY);
  }

  public async getDeviceId(): Promise<string> {
    let deviceId = await this.secureStorage.getItemAsync(DEVICE_ID_KEY);
    if (!deviceId) {
      deviceId = `dev-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
      await this.secureStorage.setItemAsync(DEVICE_ID_KEY, deviceId);
    }
    return deviceId;
  }

  /**
   * Normalized API request execution with automatic token injection,
   * version/platform/device headers, 401 single shared refresh queue, and AppError mapping.
   */
  public async request<T = any>(
    path: string,
    options: RequestInit = {},
    isRetry = false
  ): Promise<T> {
    const cleanPath = path.startsWith('/') ? path : `/${path}`;
    const url = `${this.baseUrl}${cleanPath}`;
    const deviceId = await this.getDeviceId();

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'X-App-Version': this.appVersion,
      'X-Platform': this.platform,
      'X-Device-Id': deviceId,
      ...(options.headers as Record<string, string>),
    };

    if (this.accessToken && !headers['Authorization']) {
      headers['Authorization'] = `Bearer ${this.accessToken}`;
    }

    logger.debug('ApiClient', `HTTP ${options.method || 'GET'} ${cleanPath}`);

    let response: Response;
    try {
      response = await fetch(url, {
        ...options,
        headers,
      });
    } catch (networkErr: any) {
      logger.error('ApiClient', `Network failure on ${cleanPath}`, networkErr);
      throw new AppError(
        networkErr?.message || 'Network request failed. Please check your internet connection.',
        'NETWORK_ERROR',
        0
      );
    }

    // Handle 401 Unauthorized with single shared refresh promise
    if (response.status === 401 && !isRetry && !cleanPath.includes('/auth/login') && !cleanPath.includes('/auth/refresh')) {
      logger.warn('ApiClient', `401 received on ${cleanPath}, attempting shared session refresh`);
      try {
        const newAccessToken = await this.executeSharedRefresh();
        // Retry the original request with the new access token
        return await this.request<T>(
          path,
          {
            ...options,
            headers: {
              ...(options.headers as Record<string, string>),
              Authorization: `Bearer ${newAccessToken}`,
            },
          },
          true
        );
      } catch (refreshErr: any) {
        // Refresh failed: tokens are already cleared by executeSharedRefresh
        throw refreshErr;
      }
    }

    // Parse JSON body or text
    let data: any = null;
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      try {
        data = await response.json();
      } catch {
        data = null;
      }
    } else {
      try {
        data = await response.text();
      } catch {
        data = null;
      }
    }

    if (!response.ok) {
      const error = this.normalizeError(response.status, data);
      logger.error('ApiClient', `API error ${response.status} on ${cleanPath}: ${error.code} - ${error.message}`);
      throw error;
    }

    return data as T;
  }

  /**
   * One shared refresh call for concurrent 401s (Build item 4 mutex)
   */
  private async executeSharedRefresh(): Promise<string> {
    if (this.refreshPromise) {
      return this.refreshPromise;
    }

    this.refreshPromise = (async () => {
      try {
        const refreshToken = await this.getStoredRefreshToken();
        if (!refreshToken) {
          throw new AppError('No refresh token available', 'SESSION_EXPIRED', 401);
        }

        const deviceId = await this.getDeviceId();
        const url = `${this.baseUrl}/auth/refresh`;
        const res = await fetch(url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-App-Version': this.appVersion,
            'X-Platform': this.platform,
            'X-Device-Id': deviceId,
          },
          body: JSON.stringify({ refresh: refreshToken }),
        });

        const data = await res.json().catch(() => null);

        if (!res.ok) {
          const err = this.normalizeError(res.status, data);
          await this.clearStoredTokens();

          if (err.code === 'DEVICE_REPLACED' || err.code === 'DEVICE_REVOKED') {
            this.onDeviceReplaced?.();
          } else {
            this.onSessionExpired?.();
          }
          throw err;
        }

        const newAccessToken = data.access_token;
        const newRefreshToken = data.refresh_token;

        this.setAccessToken(newAccessToken);
        if (newRefreshToken) {
          await this.setStoredRefreshToken(newRefreshToken);
        }

        return newAccessToken;
      } finally {
        this.refreshPromise = null;
      }
    })();

    return this.refreshPromise;
  }

  public normalizeError(status: number, data: any): AppError {
    let message = 'An unexpected error occurred. Please try again.';
    let code = 'UNKNOWN_ERROR';
    let details: Record<string, any> | undefined = undefined;

    if (data && typeof data === 'object') {
      if (data.message && typeof data.message === 'string') {
        message = data.message;
      } else if (data.detail && typeof data.detail === 'string') {
        message = data.detail;
      }

      if (data.code && typeof data.code === 'string') {
        code = data.code;
      } else if (status === 401) {
        code = 'UNAUTHORIZED';
      } else if (status === 403) {
        code = 'PERMISSION_DENIED';
      } else if (status === 404) {
        code = 'NOT_FOUND';
      } else if (status === 409) {
        code = 'CONFLICT';
      } else if (status === 429) {
        code = 'RATE_LIMITED';
      }

      details = data.details || (data.errors ? { errors: data.errors } : undefined);
    } else if (typeof data === 'string' && data.length > 0) {
      message = data;
    }

    return new AppError(message, code, status, details);
  }

  // --- Endpoints ---

  public async signIn(email: string, password: string, deviceName = ''): Promise<LoginResponse> {
    const deviceId = await this.getDeviceId();
    const result = await this.request<LoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({
        email,
        password,
        device_id: deviceId,
        platform: this.platform,
        app_version: this.appVersion,
        device_name: deviceName,
      }),
    });

    this.setAccessToken(result.access_token);
    await this.setStoredRefreshToken(result.refresh_token);
    return result;
  }

  public async refreshSession(): Promise<{ access_token: string; refresh_token: string }> {
    const token = await this.executeSharedRefresh();
    const refresh = (await this.getStoredRefreshToken()) || '';
    return { access_token: token, refresh_token: refresh };
  }

  public async getMe(): Promise<AuthMeResponse> {
    return await this.request<AuthMeResponse>('/auth/me');
  }

  public async signOut(): Promise<void> {
    try {
      await this.request('/auth/logout', { method: 'POST' });
    } catch (e) {
      // Best-effort logout
    } finally {
      await this.clearStoredTokens();
    }
  }

  public async requestPasswordReset(email: string): Promise<{ message: string }> {
    return await this.request('/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email }),
    });
  }

  public async verifyPasswordResetOtp(email: string, otp: string): Promise<{ message: string; reset_token?: string }> {
    return await this.request('/auth/verify-otp', {
      method: 'POST',
      body: JSON.stringify({ email, otp }),
    });
  }

  public async confirmPasswordReset(payload: {
    email: string;
    otp?: string;
    reset_token?: string;
    new_password: string;
  }): Promise<{ message: string }> {
    return await this.request('/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  public async changePassword(oldPassword: string, newPassword: string): Promise<{ message: string }> {
    return await this.request('/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({
        old_password: oldPassword,
        new_password: newPassword,
      }),
    });
  }
}

export const apiClient = new ApiClient();

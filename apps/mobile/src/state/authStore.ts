// Authentication State Slice per SDD §126, Build Item 5 & 6
import { create } from 'zustand';
import {
  AuthStatus,
  User,
  UserRole,
  AssignmentSummary,
  DeviceSummary,
  VersionPolicy,
  AppError,
} from '../domain/types';
import { isMobileAllowedRole, isWebOnlyRole } from '../domain/auth/roles';
import { ApiClient, apiClient as defaultApiClient } from '../data/api/apiClient';
import { logger } from '../platform/diagnostics';

export interface AuthState {
  status: AuthStatus;
  user: User | null;
  role: UserRole | null;
  assignment: AssignmentSummary | null;
  device: DeviceSummary | null;
  versionPolicy: VersionPolicy | null;
  isDeviceReplaced: boolean;
  isWebOnlyRole: boolean;
  isLoading: boolean;
  error: AppError | null;

  restoreSession: (client?: ApiClient) => Promise<void>;
  signIn: (identifier: string, password: string, client?: ApiClient) => Promise<void>;
  signOut: (client?: ApiClient) => Promise<void>;
  clearDeviceReplaced: () => void;
  clearError: () => void;
  setVersionPolicy: (policy: VersionPolicy) => void;
  setDeviceReplaced: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  status: 'RESTORING',
  user: null,
  role: null,
  assignment: null,
  device: null,
  versionPolicy: null,
  isDeviceReplaced: false,
  isWebOnlyRole: false,
  isLoading: false,
  error: null,

  restoreSession: async (client: ApiClient = defaultApiClient) => {
    set({ status: 'RESTORING', isLoading: true, error: null });
    logger.info('AuthStore', 'Attempting session restoration');

    try {
      const storedRefreshToken = await client.getStoredRefreshToken();
      if (!storedRefreshToken) {
        logger.info('AuthStore', 'No stored refresh token found; user is signed out');
        set({ status: 'SIGNED_OUT', isLoading: false });
        return;
      }

      // Rotate/refresh session
      await client.refreshSession();
      // Load user identity, role, assignment, device, and version policy
      const me = await client.getMe();

      const userRole = me.role;
      const isWebRole = isWebOnlyRole(userRole);

      logger.info('AuthStore', `Session restored for user ${me.user.email} with role ${userRole}`);

      set({
        status: isWebRole ? 'SIGNED_OUT' : 'SIGNED_IN',
        user: me.user,
        role: userRole,
        assignment: me.assignment,
        device: me.device,
        versionPolicy: me.version_policy,
        isWebOnlyRole: isWebRole,
        isDeviceReplaced: false,
        isLoading: false,
      });
    } catch (err: any) {
      logger.warn('AuthStore', `Session restoration failed: ${err?.message}`);
      await client.clearStoredTokens();

      const isReplaced =
        err?.code === 'DEVICE_REPLACED' ||
        err?.code === 'DEVICE_REVOKED' ||
        (err?.message && /another phone|another device/i.test(err.message));

      set({
        status: 'SIGNED_OUT',
        user: null,
        role: null,
        assignment: null,
        device: null,
        isDeviceReplaced: Boolean(isReplaced),
        isLoading: false,
        error: err instanceof AppError ? err : new AppError(err?.message || 'Session restore failed'),
      });
    }
  },

  signIn: async (identifier: string, password: string, client: ApiClient = defaultApiClient) => {
    set({ isLoading: true, error: null, isDeviceReplaced: false });
    logger.info('AuthStore', 'Initiating sign in');

    try {
      await client.signIn(identifier, password);
      const me = await client.getMe();

      const userRole = me.role;
      const isWebRole = isWebOnlyRole(userRole);

      logger.info('AuthStore', `Sign in successful for role: ${userRole}`);

      set({
        status: isWebRole ? 'SIGNED_OUT' : 'SIGNED_IN',
        user: me.user,
        role: userRole,
        assignment: me.assignment,
        device: me.device,
        versionPolicy: me.version_policy,
        isWebOnlyRole: isWebRole,
        isDeviceReplaced: false,
        isLoading: false,
      });
    } catch (err: any) {
      logger.error('AuthStore', `Sign in failed: ${err?.message}`);
      await client.clearStoredTokens();

      const isWebRoleDenied =
        err?.code === 'WRONG_CLIENT' ||
        (err?.message && /web application/i.test(err.message));

      const isReplaced =
        err?.code === 'DEVICE_REPLACED' ||
        err?.code === 'DEVICE_REVOKED';

      const appErr = err instanceof AppError ? err : new AppError(err?.message || 'Sign in failed');

      set({
        status: 'SIGNED_OUT',
        user: null,
        role: null,
        assignment: null,
        device: null,
        isWebOnlyRole: Boolean(isWebRoleDenied),
        isDeviceReplaced: Boolean(isReplaced),
        isLoading: false,
        error: appErr,
      });

      throw appErr;
    }
  },

  signOut: async (client: ApiClient = defaultApiClient) => {
    set({ isLoading: true });
    logger.info('AuthStore', 'Signing out');

    try {
      await client.signOut();
    } catch {
      // Best-effort sign out
    } finally {
      set({
        status: 'SIGNED_OUT',
        user: null,
        role: null,
        assignment: null,
        device: null,
        versionPolicy: null,
        isDeviceReplaced: false,
        isWebOnlyRole: false,
        isLoading: false,
        error: null,
      });
    }
  },

  clearDeviceReplaced: () => set({ isDeviceReplaced: false }),
  clearError: () => set({ error: null }),
  setVersionPolicy: (policy: VersionPolicy) => set({ versionPolicy: policy }),
  setDeviceReplaced: () => set({ isDeviceReplaced: true, status: 'SIGNED_OUT' }),
}));

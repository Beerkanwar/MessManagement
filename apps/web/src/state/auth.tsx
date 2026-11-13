import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { apiClient } from '../api/client';
import { UserSummary, UserRole, UserAssignmentSummary, LoginResponse, UserProfileResponse } from '../api/types';
import { getDeviceInfo } from '../lib/device';
import { env } from '../lib/env';

export interface AuthContextType {
  user: UserSummary | null;
  role: UserRole | null;
  assignment: UserAssignmentSummary | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  deviceReplaced: boolean;
  login: (email: string, password: string) => Promise<LoginResponse>;
  logout: () => Promise<void>;
  restoreSession: () => Promise<boolean>;
  dismissDeviceReplaced: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserSummary | null>(null);
  const [role, setRole] = useState<UserRole | null>(null);
  const [assignment, setAssignment] = useState<UserAssignmentSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [deviceReplaced, setDeviceReplaced] = useState(false);

  // Logout helper
  const logout = useCallback(async () => {
    try {
      await apiClient.post('/auth/logout', {});
    } catch {
      // Ignored during logout
    } finally {
      apiClient.setAccessToken(null);
      setUser(null);
      setRole(null);
      setAssignment(null);
    }
  }, []);

  // Restore session from HttpOnly refresh cookie on application startup
  const restoreSession = useCallback(async (): Promise<boolean> => {
    try {
      setIsLoading(true);
      const token = await apiClient.refreshAccessToken();
      if (!token) {
        setUser(null);
        setRole(null);
        setAssignment(null);
        return false;
      }

      // Fetch user profile
      const profile = await apiClient.get<UserProfileResponse>('/auth/me');
      setUser(profile.user);
      setRole(profile.role);
      setAssignment(profile.assignment || null);
      return true;
    } catch {
      setUser(null);
      setRole(null);
      setAssignment(null);
      return false;
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Login handler
  const login = useCallback(async (email: string, password: string): Promise<LoginResponse> => {
    setIsLoading(true);
    const deviceInfo = getDeviceInfo(env.appVersion);

    try {
      const response = await apiClient.post<LoginResponse>('/auth/login', {
        email,
        password,
        device_id: deviceInfo.device_id,
        platform: deviceInfo.platform,
        app_version: deviceInfo.app_version,
        device_name: deviceInfo.device_name,
      });

      // Keep access token ONLY in memory
      apiClient.setAccessToken(response.tokens.access);
      setUser(response.user);
      setRole(response.role);
      setAssignment(response.assignment || null);
      setDeviceReplaced(false);
      return response;
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Listen to single active device replacement
  useEffect(() => {
    const unsubDevice = apiClient.onDeviceReplaced(() => {
      setDeviceReplaced(true);
      logout();
    });

    const unsubAuth = apiClient.onAuthFailure(() => {
      setUser(null);
      setRole(null);
      setAssignment(null);
    });

    // Run initial session restoration
    restoreSession();

    return () => {
      unsubDevice();
      unsubAuth();
    };
  }, [logout, restoreSession]);

  const dismissDeviceReplaced = () => {
    setDeviceReplaced(false);
  };

  const isAuthenticated = Boolean(user && role);

  return (
    <AuthContext.Provider
      value={{
        user,
        role,
        assignment,
        isAuthenticated,
        isLoading,
        deviceReplaced,
        login,
        logout,
        restoreSession,
        dismissDeviceReplaced,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}


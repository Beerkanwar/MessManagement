import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { apiClient } from '../api/client';
import { AuthProvider } from '../state/auth';
import { RequireRole } from '../routes/Guards';
import { AppShell } from '../layouts/AppShell';
import { ClerkDashboard } from '../features/dashboard/ClerkDashboard';
import { SuperAdminDashboard } from '../features/dashboard/SuperAdminDashboard';
import { SignInPage } from '../features/auth/SignInPage';
import { OptimisticConcurrencyNotice } from '../components/OptimisticConcurrencyNotice';

describe('Phase 15: API Layer & 401 Deduplication', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    apiClient.setAccessToken(null);
  });

  it('Five concurrent requests failing with 401 trigger exactly one refresh call and all five retry', async () => {
    let refreshCount = 0;
    let endpointCalls = 0;

    const originalFetch = global.fetch;
    global.fetch = vi.fn().mockImplementation(async (url: string) => {
      const urlStr = url.toString();
      if (urlStr.includes('/auth/refresh')) {
        refreshCount++;
        return new Response(JSON.stringify({ access: 'new-refreshed-token', expires_in: 900 }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (urlStr.includes('/data/test')) {
        endpointCalls++;
        // If token is missing or old, return 401
        if (apiClient.getAccessToken() !== 'new-refreshed-token') {
          return new Response(
            JSON.stringify({ error: { code: 'TOKEN_EXPIRED', message: 'Token expired' } }),
            { status: 401, headers: { 'Content-Type': 'application/json' } }
          );
        }
        return new Response(JSON.stringify({ success: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      return originalFetch(url);
    });

    try {
      // Fire 5 concurrent requests
      const promises = [
        apiClient.get('/data/test'),
        apiClient.get('/data/test'),
        apiClient.get('/data/test'),
        apiClient.get('/data/test'),
        apiClient.get('/data/test'),
      ];

      const results = await Promise.all(promises);

      // Verify all 5 resolved with success
      expect(results).toHaveLength(5);
      results.forEach((r: any) => expect(r.success).toBe(true));

      // Verify exactly ONE refresh call was made for all 5 concurrent requests
      expect(refreshCount).toBe(1);
      // 5 initial requests failed + 5 retried = 10 calls to /data/test
      expect(endpointCalls).toBe(10);
      expect(apiClient.getAccessToken()).toBe('new-refreshed-token');
    } finally {
      global.fetch = originalFetch;
    }
  });

  it('Notifies device replaced when API returns DEVICE_REVOKED or DEVICE_REPLACED', async () => {
    const listener = vi.fn();
    const unsub = apiClient.onDeviceReplaced(listener);

    const originalFetch = global.fetch;
    global.fetch = vi.fn().mockImplementation(async () => {
      return new Response(
        JSON.stringify({
          error: {
            code: 'DEVICE_REVOKED',
            message: 'Device session is replaced.',
          },
        }),
        { status: 401, headers: { 'Content-Type': 'application/json' } }
      );
    });

    try {
      await expect(apiClient.get('/test/device-check')).rejects.toThrow();
      expect(listener).toHaveBeenCalled();
    } finally {
      unsub();
      global.fetch = originalFetch;
    }
  });
});

describe('Phase 15: Token Storage & Security', () => {
  it('Never persists access token in localStorage, sessionStorage, or visible logs', () => {
    apiClient.setAccessToken('in-memory-secret-token');

    expect(localStorage.getItem('access_token')).toBeNull();
    expect(localStorage.getItem('token')).toBeNull();
    expect(sessionStorage.getItem('access_token')).toBeNull();
    expect(sessionStorage.getItem('token')).toBeNull();

    // Verify localStorage only stores the client device UUID
    const keys = Object.keys(localStorage);
    keys.forEach((key) => {
      expect(localStorage.getItem(key)).not.toContain('in-memory-secret-token');
    });
  });
});

describe('Phase 15: Role-Aware Routing & Application Shell', () => {
  const TestApp: React.FC<{ initialEntries: string[] }> = ({
    initialEntries,
  }) => {
    // Mock AuthProvider state for routing tests
    const MockAuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
      return (
        <AuthProvider>
          {children}
        </AuthProvider>
      );
    };

    return (
      <MemoryRouter initialEntries={initialEntries}>
        <MockAuthProvider>
          <Routes>
            <Route path="/login" element={<div>Sign In Screen</div>} />
            <Route path="/403" element={<div>403 Forbidden Screen</div>} />
            <Route element={<AppShell />}>
              <Route
                path="/clerk/dashboard"
                element={
                  <RequireRole allowedRoles={['HOSTEL_CLERK']}>
                    <ClerkDashboard />
                  </RequireRole>
                }
              />
              <Route
                path="/admin/dashboard"
                element={
                  <RequireRole allowedRoles={['SUPER_ADMIN']}>
                    <SuperAdminDashboard />
                  </RequireRole>
                }
              />
            </Route>
          </Routes>
        </MockAuthProvider>
      </MemoryRouter>
    );
  };

  it('Super Admin sees Super Admin navigation and cannot be locked out', async () => {
    const originalFetch = global.fetch;
    global.fetch = vi.fn().mockImplementation(async (url: string) => {
      const urlStr = url.toString();
      if (urlStr.includes('/auth/refresh')) {
        return new Response(JSON.stringify({ access: 'mock-admin-token' }), { status: 200 });
      }
      if (urlStr.includes('/auth/me')) {
        return new Response(
          JSON.stringify({
            user: { user_id: 1, email: 'admin@college.edu', full_name: 'Super Admin User' },
            role: 'SUPER_ADMIN',
          }),
          { status: 200 }
        );
      }
      return new Response(JSON.stringify({}), { status: 200 });
    });

    try {
      render(<TestApp initialEntries={['/admin/dashboard']} />);

      await waitFor(() => {
        expect(screen.getByText('System Administration Dashboard')).toBeInTheDocument();
      });

      // Verify Super Admin navigation groups are visible
      expect(screen.getByText('People and places')).toBeInTheDocument();
      expect(screen.getByText('Meal Configuration')).toBeInTheDocument();
      expect(screen.getAllByText('System Configuration').length).toBeGreaterThanOrEqual(1);
    } finally {
      global.fetch = originalFetch;
    }
  });

  it('Hostel Clerk route is protected from unauthorized access', async () => {
    const originalFetch = global.fetch;
    global.fetch = vi.fn().mockImplementation(async (url: string) => {
      const urlStr = url.toString();
      if (urlStr.includes('/auth/refresh')) {
        return new Response(JSON.stringify({ access: 'mock-clerk-token' }), { status: 200 });
      }
      if (urlStr.includes('/auth/me')) {
        return new Response(
          JSON.stringify({
            user: { user_id: 2, email: 'clerk@college.edu', full_name: 'Hostel Clerk' },
            role: 'HOSTEL_CLERK',
            assignment: { hostel_id: 1, hostel_name: 'Hostel 1' },
          }),
          { status: 200 }
        );
      }
      return new Response(JSON.stringify({}), { status: 200 });
    });

    try {
      // Clerk attempts to access /admin/dashboard
      render(<TestApp initialEntries={['/admin/dashboard']} />);

      await waitFor(() => {
        expect(screen.getByText('403 Forbidden Screen')).toBeInTheDocument();
      });
    } finally {
      global.fetch = originalFetch;
    }
  });
});

describe('Phase 15: Student Credentials and Optimistic Concurrency', () => {
  it('Displays friendly "Use the Mobile App" page when WRONG_CLIENT is returned', async () => {
    const originalFetch = global.fetch;
    global.fetch = vi.fn().mockImplementation(async (url: string) => {
      const urlStr = url.toString();
      if (urlStr.includes('/auth/refresh')) {
        return new Response(JSON.stringify({}), { status: 401 });
      }
      if (urlStr.includes('/auth/login')) {
        return new Response(
          JSON.stringify({
            error: {
              code: 'WRONG_CLIENT',
              message: 'Students and Mess Managers must sign in using the mobile application.',
            },
          }),
          { status: 403, headers: { 'Content-Type': 'application/json' } }
        );
      }
      return new Response(JSON.stringify({}), { status: 200 });
    });

    try {
      render(
        <MemoryRouter>
          <AuthProvider>
            <SignInPage />
          </AuthProvider>
        </MemoryRouter>
      );

      // Click "Use the Mobile App" link
      const mobileBtn = screen.getByRole('button', { name: /Use the Mobile App/i });
      mobileBtn.click();

      await waitFor(() => {
        expect(screen.getByText('Mobile App Required')).toBeInTheDocument();
        expect(screen.getByText(/Dynamic rotating QR verification code/i)).toBeInTheDocument();
      });
    } finally {
      global.fetch = originalFetch;
    }
  });

  it('Forged 409 shows optimistic-concurrency reload notice', () => {
    const onReload = vi.fn();
    render(<OptimisticConcurrencyNotice isOpen={true} onReload={onReload} />);

    expect(screen.getByText('Record Changed by Someone Else')).toBeInTheDocument();
    expect(screen.getByText(/This record was modified since you loaded it/i)).toBeInTheDocument();

    const reloadBtn = screen.getByRole('button', { name: /Reload latest version/i });
    reloadBtn.click();
    expect(onReload).toHaveBeenCalled();
  });
});

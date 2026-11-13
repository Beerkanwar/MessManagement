import React, { useState, useEffect } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../state/auth';
import { CLERK_NAV, ADMIN_NAV } from './NavItems';
import { UserMenu } from '../components/UserMenu';
import { Breadcrumbs } from '../components/Breadcrumbs';
import { DeviceReplacedDialog } from '../components/DeviceReplacedDialog';
import { ReasonDialog } from '../components/ReasonDialog';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { env } from '../lib/env';
import { cn } from '../lib/utils';
import { Icons } from '../components/Icons';
import { apiClient } from '../api/client';

export const AppShell: React.FC = () => {
  const { role, deviceReplaced, dismissDeviceReplaced } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isChangePasswordOpen, setIsChangePasswordOpen] = useState(false);
  const [changePasswordSuccess, setChangePasswordSuccess] = useState<string | null>(null);
  const location = useLocation();
  const navigate = useNavigate();

  // Close mobile drawer on route navigation
  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  const navGroups = role === 'SUPER_ADMIN' ? ADMIN_NAV : CLERK_NAV;

  const handleChangePassword = async (newPasswordReason: string) => {
    try {
      await apiClient.post('/auth/change-password', {
        new_password: newPasswordReason,
      });
      setIsChangePasswordOpen(false);
      setChangePasswordSuccess('Password updated successfully.');
      setTimeout(() => setChangePasswordSuccess(null), 4000);
    } catch (err: any) {
      alert(err.message || 'Failed to change password');
    }
  };

  return (
    <div className="min-h-screen bg-bg text-text flex flex-col antialiased">
      {/* Device Replaced Modal */}
      <DeviceReplacedDialog
        isOpen={deviceReplaced}
        onSignInAgain={() => {
          dismissDeviceReplaced();
          navigate('/login');
        }}
      />

      {/* Change Password Dialog */}
      <ReasonDialog
        isOpen={isChangePasswordOpen}
        onClose={() => setIsChangePasswordOpen(false)}
        onConfirm={handleChangePassword}
        title="Change Account Password"
        description="Enter your new secure password. Must be at least 10 characters."
        placeholder="Enter new strong password..."
        confirmLabel="Update Password"
        minLength={10}
      />

      <div className="flex flex-1 relative overflow-hidden">
        {/* Mobile / Tablet Drawer Backdrop */}
        {sidebarOpen && (
          <div
            className="fixed inset-0 bg-[#0F172A]/40 z-40 lg:hidden backdrop-blur-[1px]"
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
        )}

        {/* Sidebar Navigation */}
        <aside
          className={cn(
            'fixed top-0 bottom-0 left-0 z-40 bg-surface border-r border-border transition-all duration-200 ease-out flex flex-col',
            'w-[248px] lg:w-[248px] xl:w-[248px]',
            'lg:translate-x-0',
            sidebarOpen ? 'translate-x-0 shadow-2xl' : '-translate-x-full lg:translate-x-0'
          )}
        >
          {/* Brand header */}
          <div className="h-16 px-6 border-b border-border flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-[6px] bg-primary flex items-center justify-center text-white font-bold text-[14px]">
                HM
              </div>
              <span className="font-bold text-[15px] tracking-tight text-text">
                Mess Portal
              </span>
            </div>
            <button
              type="button"
              onClick={() => setSidebarOpen(false)}
              className="lg:hidden p-1 text-text-muted hover:text-text rounded"
            >
              <Icons.X className="w-5 h-5" />
            </button>
          </div>

          {/* Navigation link groups */}
          <nav className="flex-1 overflow-y-auto p-4 space-y-6 select-none" aria-label="Main Navigation">
            {navGroups.map((group, gIdx) => (
              <div key={gIdx} className="space-y-1">
                {group.groupTitle && (
                  <h4 className="px-3 text-[11px] font-bold text-text-muted uppercase tracking-wider mb-2">
                    {group.groupTitle}
                  </h4>
                )}
                {group.items.map((item) => (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    className={({ isActive }) =>
                      cn(
                        'flex items-center gap-3 px-3 py-2 rounded-[6px] text-[13px] font-medium transition-colors',
                        isActive
                          ? 'bg-primary text-white font-semibold shadow-sm'
                          : 'text-text-secondary hover:text-text hover:bg-bg'
                      )
                    }
                  >
                    <Icons.Check className="w-4 h-4 shrink-0 opacity-70" />
                    <span className="truncate">{item.label}</span>
                  </NavLink>
                ))}
              </div>
            ))}
          </nav>

          {/* Design Gallery Link (Development shortcut) */}
          <div className="p-4 border-t border-border">
            <NavLink
              to="/gallery"
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2 px-3 py-2 rounded-[6px] text-[12px] font-medium transition-colors',
                  isActive ? 'bg-primary text-white' : 'text-text-muted hover:text-text hover:bg-bg'
                )
              }
            >
              <Icons.SlidersHorizontal className="w-4 h-4 shrink-0" />
              <span>Design System Gallery</span>
            </NavLink>
          </div>
        </aside>

        {/* Main Application Area */}
        <div className="flex-1 flex flex-col min-w-0 lg:pl-[248px]">
          {/* Top Bar */}
          <header className="h-16 bg-surface border-b border-border px-4 lg:px-8 flex items-center justify-between sticky top-0 z-30">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setSidebarOpen(true)}
                aria-label="Open navigation menu"
                className="lg:hidden p-2 rounded-[6px] text-text hover:bg-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              >
                <Icons.SlidersHorizontal className="w-5 h-5" />
              </button>

              <h1 className="text-[17px] font-semibold text-text truncate">
                Hostel Mess Management
              </h1>

              {/* Environment badge outside production */}
              {!env.isProduction && (
                <span className="ml-2 px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wider bg-warning-subtle text-warning border border-warning/30">
                  {env.environmentName}
                </span>
              )}
            </div>

            {/* User Profile Menu */}
            <UserMenu onChangePasswordClick={() => setIsChangePasswordOpen(true)} />
          </header>

          {/* System Notices / Alerts Slot */}
          {changePasswordSuccess && (
            <div className="bg-success text-white px-4 py-2 text-[13px] font-medium text-center">
              {changePasswordSuccess}
            </div>
          )}

          {/* Page Body */}
          <main className="flex-1 p-4 lg:p-8 max-w-[1280px] w-full mx-auto">
            <Breadcrumbs />
            <ErrorBoundary>
              <Outlet />
            </ErrorBoundary>
          </main>
        </div>
      </div>
    </div>
  );
};


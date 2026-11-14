import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { AppShell } from '../layouts/AppShell';
import { RequireAuth, RequireRole, PublicOnlyRoute } from './Guards';
import { SignInPage } from '../features/auth/SignInPage';
import { ForgotPasswordPage } from '../features/auth/ForgotPasswordPage';
import { ForbiddenPage } from './ForbiddenPage';
import { NotFoundPage } from './NotFoundPage';
import { ClerkDashboard } from '../features/dashboard/ClerkDashboard';
import { SuperAdminDashboard } from '../features/dashboard/SuperAdminDashboard';
import { ComponentGallery } from '../gallery/ComponentGallery';
import { FeaturePlaceholder } from '../features/common/FeaturePlaceholder';
import { StudentVerificationPage } from '../features/clerk/StudentVerificationPage';
import { MenuPage } from '../features/clerk/MenuPage';
import { ExtraItemsPage } from '../features/clerk/ExtraItemsPage';
import { AttendancePage } from '../features/clerk/AttendancePage';
import { BillsPage } from '../features/clerk/BillsPage';
import { FeedbackPage } from '../features/clerk/FeedbackPage';
import { ReportsPage } from '../features/clerk/ReportsPage';
import { useAuth } from '../state/auth';

const RootRedirect: React.FC = () => {
  const { role, isAuthenticated, isLoading } = useAuth();
  if (isLoading) return null;
  if (!isAuthenticated || !role) {
    return <Navigate to="/login" replace />;
  }
  if (role === 'SUPER_ADMIN') {
    return <Navigate to="/admin/dashboard" replace />;
  }
  if (role === 'HOSTEL_CLERK') {
    return <Navigate to="/clerk/dashboard" replace />;
  }
  return <Navigate to="/403" replace />;
};

export const AppRoutes: React.FC = () => {
  return (
    <Routes>
      {/* Public Routes */}
      <Route
        path="/login"
        element={
          <PublicOnlyRoute>
            <SignInPage />
          </PublicOnlyRoute>
        }
      />
      <Route
        path="/forgot-password"
        element={
          <PublicOnlyRoute>
            <ForgotPasswordPage />
          </PublicOnlyRoute>
        }
      />
      <Route path="/403" element={<ForbiddenPage />} />
      <Route path="/gallery" element={<ComponentGallery />} />

      {/* Authenticated Root */}
      <Route path="/" element={<RootRedirect />} />

      {/* Protected Routes inside AppShell */}
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        {/* Hostel Clerk Routes (Phase 16 target) */}
        <Route
          path="clerk"
          element={
            <RequireRole allowedRoles={['HOSTEL_CLERK']}>
              <Navigate to="/clerk/dashboard" replace />
            </RequireRole>
          }
        />
        <Route
          path="clerk/dashboard"
          element={
            <RequireRole allowedRoles={['HOSTEL_CLERK']}>
              <ClerkDashboard />
            </RequireRole>
          }
        />
        <Route
          path="clerk/verifications"
          element={
            <RequireRole allowedRoles={['HOSTEL_CLERK']}>
              <StudentVerificationPage />
            </RequireRole>
          }
        />
        <Route
          path="clerk/menu"
          element={
            <RequireRole allowedRoles={['HOSTEL_CLERK']}>
              <MenuPage />
            </RequireRole>
          }
        />
        <Route
          path="clerk/extras"
          element={
            <RequireRole allowedRoles={['HOSTEL_CLERK']}>
              <ExtraItemsPage />
            </RequireRole>
          }
        />
        <Route
          path="clerk/attendance"
          element={
            <RequireRole allowedRoles={['HOSTEL_CLERK']}>
              <AttendancePage />
            </RequireRole>
          }
        />
        <Route
          path="clerk/bills"
          element={
            <RequireRole allowedRoles={['HOSTEL_CLERK']}>
              <BillsPage />
            </RequireRole>
          }
        />
        <Route
          path="clerk/feedback"
          element={
            <RequireRole allowedRoles={['HOSTEL_CLERK']}>
              <FeedbackPage />
            </RequireRole>
          }
        />
        <Route
          path="clerk/reports"
          element={
            <RequireRole allowedRoles={['HOSTEL_CLERK']}>
              <ReportsPage />
            </RequireRole>
          }
        />

        {/* Super Admin Routes (Phase 17 target) */}
        <Route
          path="admin"
          element={
            <RequireRole allowedRoles={['SUPER_ADMIN']}>
              <Navigate to="/admin/dashboard" replace />
            </RequireRole>
          }
        />
        <Route
          path="admin/dashboard"
          element={
            <RequireRole allowedRoles={['SUPER_ADMIN']}>
              <SuperAdminDashboard />
            </RequireRole>
          }
        />
        <Route
          path="admin/hostels"
          element={
            <RequireRole allowedRoles={['SUPER_ADMIN']}>
              <FeaturePlaceholder
                title="Hostels Master"
                description="Manage hostel properties, clerk bindings, and mess attachments"
                phaseTarget="Phase 17"
              />
            </RequireRole>
          }
        />
        <Route
          path="admin/messes"
          element={
            <RequireRole allowedRoles={['SUPER_ADMIN']}>
              <FeaturePlaceholder
                title="Messes Master"
                description="Mess facilities, manager assignments, and dining limits"
                phaseTarget="Phase 17"
              />
            </RequireRole>
          }
        />
        <Route
          path="admin/students"
          element={
            <RequireRole allowedRoles={['SUPER_ADMIN']}>
              <FeaturePlaceholder
                title="Students Registry"
                description="Student roster, active assignments, and balance ledger"
                phaseTarget="Phase 17"
              />
            </RequireRole>
          }
        />
        <Route
          path="admin/clerks"
          element={
            <RequireRole allowedRoles={['SUPER_ADMIN']}>
              <FeaturePlaceholder
                title="Hostel Clerks"
                description="Clerk user accounts and single-hostel scopes"
                phaseTarget="Phase 17"
              />
            </RequireRole>
          }
        />
        <Route
          path="admin/managers"
          element={
            <RequireRole allowedRoles={['SUPER_ADMIN']}>
              <FeaturePlaceholder
                title="Mess Managers"
                description="Manager accounts, DEC-21 assignments, and device sync status"
                phaseTarget="Phase 17"
              />
            </RequireRole>
          }
        />
        <Route
          path="admin/meal-config"
          element={
            <RequireRole allowedRoles={['SUPER_ADMIN']}>
              <FeaturePlaceholder
                title="Meal Configuration & Occurrences"
                description="35-day scheduled occurrences, cancellations, and timing"
                phaseTarget="Phase 17"
              />
            </RequireRole>
          }
        />
        <Route
          path="admin/pricing"
          element={
            <RequireRole allowedRoles={['SUPER_ADMIN']}>
              <FeaturePlaceholder
                title="Common Meal Rates"
                description="Effective-dated daily common rate per mess"
                phaseTarget="Phase 17"
              />
            </RequireRole>
          }
        />
        <Route
          path="admin/billing"
          element={
            <RequireRole allowedRoles={['SUPER_ADMIN']}>
              <FeaturePlaceholder
                title="Billing Periods & Runs"
                description="Monthly cycle locks, adjustment audits, and ledger posting"
                phaseTarget="Phase 17"
              />
            </RequireRole>
          }
        />
        <Route
          path="admin/devices"
          element={
            <RequireRole allowedRoles={['SUPER_ADMIN']}>
              <FeaturePlaceholder
                title="Device Registrations"
                description="Active manager and clerk device bindings, session revocation"
                phaseTarget="Phase 17"
              />
            </RequireRole>
          }
        />
        <Route
          path="admin/sync"
          element={
            <RequireRole allowedRoles={['SUPER_ADMIN']}>
              <FeaturePlaceholder
                title="Synchronization & Conflicts"
                description="Offline manager sync queue, conflict resolution, and change cursors"
                phaseTarget="Phase 17"
              />
            </RequireRole>
          }
        />
        <Route
          path="admin/reports"
          element={
            <RequireRole allowedRoles={['SUPER_ADMIN']}>
              <FeaturePlaceholder
                title="Central Reports"
                description="Cross-hostel consumption, bill summaries, and export runs"
                phaseTarget="Phase 17"
              />
            </RequireRole>
          }
        />
        <Route
          path="admin/audit"
          element={
            <RequireRole allowedRoles={['SUPER_ADMIN']}>
              <FeaturePlaceholder
                title="System Audit Logs"
                description="Immutable audit trail of all sensitive events"
                phaseTarget="Phase 17"
              />
            </RequireRole>
          }
        />
        <Route
          path="admin/settings"
          element={
            <RequireRole allowedRoles={['SUPER_ADMIN']}>
              <FeaturePlaceholder
                title="System Configuration"
                description="Effective-dated system settings and app version policies"
                phaseTarget="Phase 17"
              />
            </RequireRole>
          }
        />
      </Route>

      {/* 404 Catch-All */}
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
};
export default AppRoutes;


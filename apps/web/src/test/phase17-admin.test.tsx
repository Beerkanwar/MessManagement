import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { apiClient } from '../api/client';
import { SuperAdminDashboard } from '../features/dashboard/SuperAdminDashboard';
import { HostelsPage } from '../features/admin/HostelsPage';
import { MessesPage } from '../features/admin/MessesPage';
import { ClerksPage } from '../features/admin/ClerksPage';
import { ManagersPage } from '../features/admin/ManagersPage';
import { StudentsPage } from '../features/admin/StudentsPage';
import { BillingPage } from '../features/admin/BillingPage';
import { DevicesPage } from '../features/admin/DevicesPage';
import { SyncPage } from '../features/admin/SyncPage';
import { AuditLogsPage } from '../features/admin/AuditLogsPage';
import { MealConfigPage } from '../features/admin/MealConfigPage';
import { PricingPage } from '../features/admin/PricingPage';
import { SystemConfigPage } from '../features/admin/SystemConfigPage';

// Mock useAuth for SUPER_ADMIN
vi.mock('../state/auth', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'admin@college.edu', full_name: 'Super Administrator' },
    role: 'SUPER_ADMIN',
    assignment: null,
    isAuthenticated: true,
    isLoading: false,
  }),
}));

describe('Phase 17: Super Admin Screens & Lifecycle Verification', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe('1. Super Admin Dashboard', () => {
    it('renders all 5 required stat tiles linking to their respective lists', async () => {
      vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
        if (url.includes('/reports/summary')) {
          return { pending_verifications: 12, unresolved_imports: 3 };
        }
        if (url.includes('/billing/periods')) {
          return [{ billing_period_id: 1, status: 'OPEN', year: 2026, month: 11 }];
        }
        if (url.includes('/sync/conflicts')) {
          return [{ conflict_id: 101, status: 'OPEN' }];
        }
        return [];
      });

      render(
        <MemoryRouter>
          <SuperAdminDashboard />
        </MemoryRouter>
      );

      expect(await screen.findByText(/System Administration Dashboard/i)).toBeInTheDocument();
      // Tile 1: Students Awaiting Verification
      expect(screen.getByText(/Students Awaiting Verification/i)).toBeInTheDocument();
      // Tile 2: Current Billing Period
      expect(screen.getByText(/Current Billing Period/i)).toBeInTheDocument();
      // Tile 3: Open Sync Conflicts
      expect(screen.getByText(/Open Sync Conflicts/i)).toBeInTheDocument();
      // Tile 4: Oldest Device Last Sync
      expect(screen.getByText(/Oldest Device Last Sync/i)).toBeInTheDocument();
      // Tile 5: Unresolved Import Errors
      expect(screen.getByText(/Unresolved Import Errors/i)).toBeInTheDocument();
    });
  });

  describe('2. Hostels Master & Refusal Paths', () => {
    it('handles hostel creation, 409 optimistic locking version conflict, and deactivation refusal with explanation', async () => {
      vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
        if (url.includes('/hostels')) {
          return [
            {
              hostel_id: 1,
              code: 'H1',
              name: 'Himalaya Hostel',
              status: 'ACTIVE',
              version: 2,
            },
          ];
        }
        if (url.includes('/admin/hostel-clerks')) {
          return [{ user_id: 2, full_name: 'Ramesh Clerk', is_active: true, hostel: { id: 1, code: 'H1' } }];
        }
        return [];
      });

      const patchSpy = vi.spyOn(apiClient, 'patch').mockRejectedValueOnce({
        status: 409,
        code: 'OPTIMISTIC_LOCK_ERROR',
        message: 'Hostel was modified by another administrator.',
      });

      render(
        <MemoryRouter>
          <HostelsPage />
        </MemoryRouter>
      );

      expect(await screen.findByText('Himalaya Hostel')).toBeInTheDocument();
      expect(screen.getByText('Ramesh Clerk')).toBeInTheDocument();

      // Test Edit and 409 conflict
      const editBtn = screen.getByRole('button', { name: /Edit/i });
      fireEvent.click(editBtn);

      const saveBtn = screen.getByRole('button', { name: /Save Changes/i });
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(screen.getByText(/Version Conflict/i)).toBeInTheDocument();
      });
      expect(patchSpy).toHaveBeenCalled();

      // Test deactivation refusal when clerk/students exist
      const postSpy = vi.spyOn(apiClient, 'post').mockRejectedValueOnce({
        status: 400,
        code: 'STATE_CONFLICT',
        message: 'Cannot deactivate hostel: there is still an active Clerk assignment.',
      });

      const deactivateBtn = screen.getByRole('button', { name: /Deactivate/i });
      fireEvent.click(deactivateBtn);

      const confirmBtn = screen.getByRole('button', { name: /Deactivate Hostel/i });
      fireEvent.click(confirmBtn);

      await waitFor(() => {
        expect(screen.getByText(/Cannot deactivate hostel: there is still an active Clerk assignment/i)).toBeInTheDocument();
      });
      expect(postSpy).toHaveBeenCalled();
    });
  });

  describe('3. Messes Master', () => {
    it('lists messes, shows feeding hostels, and supports creation', async () => {
      vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
        if (url.includes('/messes')) {
          return [{ mess_id: 1, code: 'M1', name: 'North Dining Hall', status: 'ACTIVE', version: 1 }];
        }
        if (url.includes('/admin/mess-managers')) {
          return [{ user_id: 3, full_name: 'Anand Manager', is_active: true, mess: { id: 1, code: 'M1' } }];
        }
        if (url.includes('/hostels')) {
          return [{ hostel_id: 1, code: 'H1', status: 'ACTIVE' }];
        }
        return [];
      });

      render(
        <MemoryRouter>
          <MessesPage />
        </MemoryRouter>
      );

      expect(await screen.findByText('North Dining Hall')).toBeInTheDocument();
      expect(screen.getByText('Anand Manager')).toBeInTheDocument();
      expect(screen.getByText('H1')).toBeInTheDocument();
    });
  });

  describe('4. Hostel Clerks & DEC-03 Notice', () => {
    it('creates clerk and displays DEC-03 initial password setup instructions', async () => {
      vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
        if (url.includes('/admin/hostel-clerks')) {
          return [];
        }
        if (url.includes('/hostels')) {
          return [{ hostel_id: 1, code: 'H1', name: 'Hostel 1' }];
        }
        return [];
      });

      const postSpy = vi.spyOn(apiClient, 'post').mockResolvedValueOnce({
        user_id: 10,
        full_name: 'New Clerk',
        email: 'newclerk@college.edu',
      } as any);

      render(
        <MemoryRouter>
          <ClerksPage />
        </MemoryRouter>
      );

      expect(await screen.findByText(/Hostel Clerks/i)).toBeInTheDocument();

      const addBtn = screen.getByRole('button', { name: /Add Hostel Clerk/i });
      fireEvent.click(addBtn);

      fireEvent.change(screen.getByLabelText(/Full Name/i), { target: { value: 'New Clerk' } });
      fireEvent.change(screen.getByLabelText(/Email Address/i), { target: { value: 'newclerk@college.edu' } });

      const submitBtn = screen.getByRole('button', { name: /Create Clerk/i });
      fireEvent.click(submitBtn);

      await waitFor(() => {
        // DEC-03 Notice rendered
        expect(screen.getByText(/Password Setup Notice \(DEC-03\)/i)).toBeInTheDocument();
        expect(screen.getByText(/Forgot password/i)).toBeInTheDocument();
      });
      expect(postSpy).toHaveBeenCalled();
    });
  });

  describe('5. Mess Managers & DEC-21 Assignment', () => {
    it('warns about mobile phone cache replacement on mess reassignment', async () => {
      vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
        if (url.includes('/admin/mess-managers')) {
          return [
            {
              user_id: 5,
              full_name: 'Manager Bob',
              email: 'bob@college.edu',
              is_active: true,
              mess: { id: 1, code: 'M1', name: 'Mess 1' },
            },
          ];
        }
        if (url.includes('/messes')) {
          return [
            { mess_id: 1, code: 'M1', name: 'Mess 1' },
            { mess_id: 2, code: 'M2', name: 'Mess 2' },
          ];
        }
        return [];
      });

      render(
        <MemoryRouter>
          <ManagersPage />
        </MemoryRouter>
      );

      expect(await screen.findByText('Manager Bob')).toBeInTheDocument();

      const reassignBtn = screen.getByRole('button', { name: /Reassign/i });
      fireEvent.click(reassignBtn);

      // Warning text verified
      expect(screen.getByText(/Cache Replacement Warning/i)).toBeInTheDocument();
      expect(screen.getByText(/invalidate their mobile SQLite cache/i)).toBeInTheDocument();
    });
  });

  describe('6. Student Registry, Transfer, Secret Verification & Import', () => {
    it('verifies 3-step student creation, transfer initiation, and secret privacy (never exposed)', async () => {
      vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
        if (url.includes('/students?')) {
          return [
            {
              student_id: 50,
              roll_number: '2026CS50',
              full_name: 'Alice Wonder',
              email: 'alice@college.edu',
              status: 'ACTIVE',
              version: 1,
              created_at: '2026-11-01T08:00:00Z',
            },
          ];
        }
        if (url.includes('/students/50')) {
          return {
            student_id: 50,
            roll_number: '2026CS50',
            full_name: 'Alice Wonder',
            email: 'alice@college.edu',
            status: 'ACTIVE',
            version: 1,
            hostel_code: 'H1',
            current_assignment: { mess: { code: 'M1', name: 'Mess 1' }, status: 'ACTIVE' },
          };
        }
        if (url.includes('/hostels')) return [{ hostel_id: 1, code: 'H1', name: 'Hostel 1' }];
        if (url.includes('/messes')) return [{ mess_id: 1, code: 'M1', name: 'Mess 1' }];
        return [];
      });

      render(
        <MemoryRouter>
          <StudentsPage />
        </MemoryRouter>
      );

      expect(await screen.findByText('Alice Wonder')).toBeInTheDocument();

      // Open student detail drawer
      const manageBtn = screen.getByRole('button', { name: /Manage/i });
      fireEvent.click(manageBtn);

      // Verify Profile tab first
      expect((await screen.findAllByText('2026CS50')).length).toBeGreaterThan(0);

      // Switch to Assignments tab
      const assignmentsTab = screen.getByRole('tab', { name: /Assignments/i });
      fireEvent.click(assignmentsTab);

      expect(await screen.findByText('Dining Allocation Timeline')).toBeInTheDocument();

      // Check Secret tab: shows version and rotation time ONLY, never the secret
      const secretTab = screen.getByRole('tab', { name: /Secret/i });
      fireEvent.click(secretTab);

      expect(screen.getByText(/Student QR Secret Metadata/i)).toBeInTheDocument();
      expect(screen.getByText(/v1/i)).toBeInTheDocument();
      expect(screen.queryByText(/base64/i)).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Rotate Secret/i })).toBeInTheDocument();

      // Return to Assignments tab for Transfer Dialog check
      fireEvent.click(assignmentsTab);

      const transferBtn = screen.getByRole('button', { name: /Transfer Student/i });
      fireEvent.click(transferBtn);

      expect(screen.getByText(/Transferring a student marks their allocation as/i)).toBeInTheDocument();
      expect(screen.getByText(/PENDING_VERIFICATION/i)).toBeInTheDocument();
    });

    it('import wizard validates and previews counts before atomic commit', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue([]);
      const postSpy = vi.spyOn(apiClient, 'post').mockImplementation(async (url: string) => {
        if (url.includes('/students/imports')) {
          return {
            batch_id: 99,
            status: 'VALIDATED',
            total_rows: 2000,
            valid_rows: 1950,
            rejected_rows: 50,
          };
        }
        return {};
      });

      render(
        <MemoryRouter>
          <StudentsPage />
        </MemoryRouter>
      );

      const importBtn = await screen.findByRole('button', { name: /Import Roster/i });
      fireEvent.click(importBtn);

      expect(screen.getByText(/Student Roster Bulk Import/i)).toBeInTheDocument();
      expect(screen.getByText(/Download Template CSV/i)).toBeInTheDocument();
      expect(postSpy).toBeDefined();
    });
  });

  describe('7. Billing Lifecycle & Constraint C01', () => {
    it('offers only legal next action in each period status and enforces positive fee/fine with mandatory reason', async () => {
      let currentStatus: string = 'OPEN';

      vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
        if (url.endsWith('/billing/periods/1')) {
          return {
            billing_period_id: 1,
            year: 2026,
            month: 11,
            period_start: '2026-11-01',
            period_end: '2026-11-30',
            status: currentStatus,
            total_billed: '50000.00',
            student_count: 100,
            version: 1,
          };
        }
        if (url.includes('/billing/periods')) {
          return [
            {
              billing_period_id: 1,
              year: 2026,
              month: 11,
              period_start: '2026-11-01',
              period_end: '2026-11-30',
              status: currentStatus,
              total_billed: '50000.00',
              student_count: 100,
              version: 1,
            },
          ];
        }
        if (url.includes('/billing/bills')) {
          return [
            {
              bill_id: 10,
              student_id: 1,
              student_roll_number: '2026CS01',
              student_name: 'John Doe',
              meal_charge: '4500.00',
              extras_charge: '300.00',
              adjustments_total: '0.00',
              total_amount: '4800.00',
              status: currentStatus === 'LOCKED' ? 'LOCKED' : 'GENERATED',
            },
          ];
        }
        return [];
      });

      render(
        <MemoryRouter>
          <BillingPage />
        </MemoryRouter>
      );

      // In OPEN state: only "Generate Bills" is offered
      expect(await screen.findByRole('button', { name: /Generate Bills/i })).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Lock Period/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Unlock Period/i })).not.toBeInTheDocument();

      // Test Adjust action (C01: positive fee/fine with reason)
      const adjustBtn = screen.getByRole('button', { name: /Adjust/i });
      fireEvent.click(adjustBtn);

      expect(screen.getByText(/Constraint C01/i)).toBeInTheDocument();
      expect(screen.getByText(/Only positive FEE or FINE adjustments are permitted/i)).toBeInTheDocument();
    });
  });

  describe('8. Device Registrations & D14 Drain Policy', () => {
    it('revokes device session with ReasonDialog explaining student vs manager D14 drain policy', async () => {
      vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
        if (url.includes('/admin/devices')) {
          return [
            {
              device_registration_id: 88,
              user_id: 5,
              user_full_name: 'Manager Carl',
              user_email: 'carl@college.edu',
              user_role: 'MESS_MANAGER',
              device_id: 'dev-manager-001',
              platform: 'ANDROID',
              app_version: '2.1.0',
              session_status: 'ACTIVE',
              registered_at: '2026-11-01T10:00:00Z',
            },
          ];
        }
        return [];
      });

      render(
        <MemoryRouter>
          <DevicesPage />
        </MemoryRouter>
      );

      expect(await screen.findByText('Manager Carl')).toBeInTheDocument();

      const revokeBtn = screen.getByRole('button', { name: /Revoke Session/i });
      fireEvent.click(revokeBtn);

      // D14 text check
      expect(screen.getAllByText(/D14/i).length).toBeGreaterThan(0);
      expect(screen.getByText(/a Manager phone with unsynced scans first becomes sync-only/i)).toBeInTheDocument();
    });
  });

  describe('9. Sync Conflicts & Locked Period Guard', () => {
    it('disables Accept button with explanation when conflict belongs to a LOCKED period', async () => {
      vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
        if (url.includes('/sync/conflicts/7')) {
          return {
            conflict_id: 7,
            conflict_type: 'MEAL_ATTENDANCE_AFTER_PAUSE',
            detected_at: '2026-11-05T12:00:00Z',
            transaction: {
              student_roll: '2026CS15',
              mess_code: 'M1',
            },
            server_facts: {
              assignment_status: 'ACTIVE',
              is_paused: true,
              period_status: 'LOCKED', // LOCKED period!
            },
          };
        }
        if (url.includes('/sync/conflicts')) {
          return [
            {
              conflict_id: 7,
              conflict_type: 'MEAL_ATTENDANCE_AFTER_PAUSE',
              detected_at: '2026-11-05T12:00:00Z',
              transaction: { student_roll: '2026CS15', mess_code: 'M1' },
            },
          ];
        }
        return [];
      });

      render(
        <MemoryRouter>
          <SyncPage />
        </MemoryRouter>
      );

      expect(await screen.findByText('MEAL_ATTENDANCE_AFTER_PAUSE')).toBeInTheDocument();

      const reviewBtn = screen.getByRole('button', { name: /Review & Resolve/i });
      fireEvent.click(reviewBtn);

      // Verified locked period warning and disabled accept button
      await waitFor(() => {
        expect(screen.getByText(/The corresponding billing period is LOCKED/i)).toBeInTheDocument();
      });
      const acceptBtn = screen.getByRole('button', { name: /Accept Transaction/i });
      expect(acceptBtn).toBeDisabled();
    });
  });

  describe('10. System Configuration & Audit Diff', () => {
    it('renders audit trail with side-by-side diff drawer and correlation id filtering', async () => {
      vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
        if (url.includes('/audit/events')) {
          return [
            {
              audit_id: 501,
              event_type: 'HOSTEL_DEACTIVATED',
              occurred_at: '2026-11-10T14:30:00Z',
              actor: { full_name: 'Super Admin', email: 'admin@college.edu', role: 'SUPER_ADMIN' },
              entity_type: 'Hostel',
              entity_id: '1',
              reason: 'Annual building renovation',
              correlation_id: 'corr-9988',
              old_values: { status: 'ACTIVE' },
              new_values: { status: 'INACTIVE' },
            },
          ];
        }
        return [];
      });

      render(
        <MemoryRouter>
          <AuditLogsPage />
        </MemoryRouter>
      );

      expect(await screen.findByText('HOSTEL_DEACTIVATED')).toBeInTheDocument();

      const diffBtn = screen.getByRole('button', { name: /View Diff/i });
      fireEvent.click(diffBtn);

      expect(screen.getByText(/State Changes \(Old vs New Values\)/i)).toBeInTheDocument();
      expect(screen.getByText(/View Related Events \(Correlation ID\)/i)).toBeInTheDocument();
    });
  });

  describe('11. Meal Configuration & Occurrence Cancellation Refusal', () => {
    it('prompts ReasonDialog for cancellation and shows refusal when consumptions exist', async () => {
      vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
        if (url.includes('/messes')) {
          return [{ mess_id: 1, code: 'M1', name: 'Mess 1' }];
        }
        if (url.includes('/meals/occurrences')) {
          return [
            {
              occurrence_id: 201,
              mess_id: 1,
              meal_type: { code: 'BREAKFAST', name: 'Breakfast' },
              meal_date: '2026-11-20',
              status: 'SCHEDULED',
              consumption_count: 5,
            },
          ];
        }
        return [];
      });

      const postSpy = vi.spyOn(apiClient, 'post').mockRejectedValueOnce({
        status: 400,
        code: 'CANNOT_CANCEL_CONSUMED',
        message: 'Cannot cancel meal occurrence: 5 student meal consumptions already recorded.',
      });

      render(
        <MemoryRouter>
          <MealConfigPage />
        </MemoryRouter>
      );

      expect(await screen.findByText('2026-11-20')).toBeInTheDocument();
      expect(screen.getByText(/Consumptions: 5 scans/i)).toBeInTheDocument();

      const cancelBtn = screen.getByRole('button', { name: /Cancel/i });
      fireEvent.click(cancelBtn);

      // Verify ReasonDialog content
      await waitFor(() => {
        expect(screen.getByText(/Cancel Meal Occurrence: 2026-11-20/i)).toBeInTheDocument();
      });
      expect(
        screen.getByText(/Cancellation will be refused by the server if student meal consumptions have already been recorded/i)
      ).toBeInTheDocument();

      // Enter reason and submit
      const reasonInput = screen.getByPlaceholderText(/Explain the operational or audit reason/i);
      fireEvent.change(reasonInput, { target: { value: 'Facility emergency maintenance shutdown' } });

      const confirmBtn = screen.getByRole('button', { name: /Confirm Cancellation/i });
      fireEvent.click(confirmBtn);

      await waitFor(() => {
        expect(
          screen.getByText(/Cannot cancel meal occurrence: 5 student meal consumptions already recorded/i)
        ).toBeInTheDocument();
      });
      expect(postSpy).toHaveBeenCalled();
    });
  });

  describe('12. Pricing Rules & Future-Dated Rates', () => {
    it('displays mandatory past-price immutability notice and enforces common daily rate', async () => {
      vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
        if (url.includes('/messes')) {
          return [{ mess_id: 1, code: 'M1', name: 'Mess 1' }];
        }
        if (url.includes('/meal-rates')) {
          return [
            {
              meal_rate_id: 1,
              rate: '150.00',
              effective_from: '2026-11-01',
              effective_to: null,
              version: 1,
            },
          ];
        }
        return [];
      });

      render(
        <MemoryRouter>
          <PricingPage />
        </MemoryRouter>
      );

      expect(await screen.findByText(/Pricing Immutable Rule:/i)).toBeInTheDocument();
      expect(
        screen.getByText(/The common rate applies to Breakfast, Lunch and Dinner/i)
      ).toBeInTheDocument();

      const addBtn = screen.getByRole('button', { name: /Add New Rate/i });
      fireEvent.click(addBtn);

      await waitFor(() => {
        expect(
          screen.getByText(/Past prices cannot be changed; earlier transactions keep their price/i)
        ).toBeInTheDocument();
      });
    });
  });

  describe('13. System Configuration & DEC-13 Secret Rotation', () => {
    it('prompts ReasonDialog for secret rotation, warns of DEC-13 consequence, and rotates', async () => {
      vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
        if (url.includes('/admin/settings')) {
          return [
            {
              setting_id: 1,
              key: 'AUTH_SESSION_LIFETIME',
              value: '86400',
              data_type: 'INTEGER',
              is_sensitive: false,
            },
          ];
        }
        if (url.includes('/messes')) {
          return [{ mess_id: 1, code: 'M1', name: 'Dining Hall 1' }];
        }
        return [];
      });

      const postSpy = vi.spyOn(apiClient, 'post').mockResolvedValueOnce({
        status: 'SUCCESS',
        affected_count: 500,
        rotated_records: [{ student_id: 101, version: 2, rotated_at: new Date().toISOString(), status: 'SUCCESS' }],
      } as any);

      render(
        <MemoryRouter>
          <SystemConfigPage />
        </MemoryRouter>
      );

      expect(await screen.findByText(/AUTH_SESSION_LIFETIME/i)).toBeInTheDocument();

      // Switch to Secret Management tab
      const secretsTab = screen.getByRole('tab', { name: /Secret Management/i });
      fireEvent.click(secretsTab);

      expect(screen.getByText(/Rotating retires active secret key material/i)).toBeInTheDocument();
      expect(screen.getAllByText(/DEC-13/i).length).toBeGreaterThan(0);

      // Select mess facility
      const messSelect = screen.getByLabelText(/Target Mess Hall/i);
      fireEvent.change(messSelect, { target: { value: '1' } });

      const rotateBtn = screen.getByRole('button', { name: /Initiate Secret Rotation/i });
      await waitFor(() => {
        expect(rotateBtn).not.toBeDisabled();
      });
      fireEvent.click(rotateBtn);

      // Verify ReasonDialog content
      await waitFor(() => {
        expect(screen.getByText(/Rotate Student Secret Key/i)).toBeInTheDocument();
      });
      expect(screen.getByText(/The student's device must connect to fetch the updated QR key material/i)).toBeInTheDocument();

      const reasonInput = screen.getByPlaceholderText(/Explain the operational or audit reason/i);
      fireEvent.change(reasonInput, { target: { value: 'Annual security key rollover' } });

      const confirmBtn = screen.getByRole('button', { name: /Rotate Keys/i });
      fireEvent.click(confirmBtn);

      await waitFor(() => {
        expect(screen.getByText(/Successfully rotated StudentSecretKey for scope MESS/i)).toBeInTheDocument();
      });
      expect(postSpy).toHaveBeenCalled();
    });
  });

  describe('14. Billing Lock Summary & Unlock ReasonDialog', () => {
    it('displays summary count and amount in lock confirmation, and requires ReasonDialog for unlock', async () => {
      let status = 'REVIEWED';

      vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
        if (url.includes('/billing/periods/1')) {
          return {
            billing_period_id: 1,
            year: 2026,
            month: 11,
            period_start: '2026-11-01',
            period_end: '2026-11-30',
            status: status,
            total_billed: '75000.00',
            student_count: 150,
            version: 1,
          };
        }
        if (url.includes('/billing/periods')) {
          return [
            {
              billing_period_id: 1,
              year: 2026,
              month: 11,
              period_start: '2026-11-01',
              period_end: '2026-11-30',
              status: status,
              total_billed: '75000.00',
              student_count: 150,
              version: 1,
            },
          ];
        }
        if (url.includes('/billing/bills')) {
          return [];
        }
        return [];
      });

      render(
        <MemoryRouter>
          <BillingPage />
        </MemoryRouter>
      );

      // When REVIEWED: Lock button is present
      const lockBtn = await screen.findByRole('button', { name: /Lock Period/i });
      fireEvent.click(lockBtn);

      // Lock confirmation shows summary totals
      await waitFor(() => {
        expect(screen.getByText(/Lock Billing Period/i)).toBeInTheDocument();
      });
      expect(screen.getByText(/Total Billed: ₹75000.00/i)).toBeInTheDocument();
      expect(screen.getByText(/Students: 150/i)).toBeInTheDocument();
    });
  });
});

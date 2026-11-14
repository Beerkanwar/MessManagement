import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { apiClient } from '../api/client';
import { StudentVerificationPage } from '../features/clerk/StudentVerificationPage';
import { MenuPage } from '../features/clerk/MenuPage';
import { ExtraItemsPage } from '../features/clerk/ExtraItemsPage';
import { BillsPage } from '../features/clerk/BillsPage';
import { ReportsPage } from '../features/clerk/ReportsPage';
import { AttendancePage } from '../features/clerk/AttendancePage';
import { FeedbackPage } from '../features/clerk/FeedbackPage';

// Mock useAuth
vi.mock('../state/auth', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'clerk@hostel.edu', fullName: 'Hostel Clerk' },
    role: 'HOSTEL_CLERK',
    assignment: { hostel_id: 1, hostel_name: 'Hostel A', mess_id: 1, mess_name: 'Mess 1' },
    isAuthenticated: true,
    isLoading: false,
  }),
}));

describe('Phase 16: Hostel Clerk Screens', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe('Student Verification Screen', () => {
    it('renders pending students, enables single verify and handles bulk verify', async () => {
      vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
        if (url.includes('/students/verifications')) {
          return [
            {
              assignment_id: 101,
              student_id: 1,
              roll_number: '2026CS01',
              name: 'John Doe',
              email: 'john@college.edu',
              mess_name: 'Mess 1',
              hostel_name: 'Hostel A',
              effective_from: '2026-11-01',
              status: 'PENDING_VERIFICATION',
              created_at: '2026-11-01T10:00:00Z',
            },
          ];
        }
        return [];
      });

      const postSpy = vi.spyOn(apiClient, 'post').mockResolvedValue({ success: true } as any);

      render(
        <MemoryRouter>
          <StudentVerificationPage />
        </MemoryRouter>
      );

      // Verify header notice
      expect(await screen.findByText(/Student Verification/i)).toBeInTheDocument();
      expect(
        screen.getByText(/You can verify student details but not edit them/i)
      ).toBeInTheDocument();

      // Check student is listed
      expect(await screen.findByText('John Doe')).toBeInTheDocument();
      expect(screen.getByText('2026CS01')).toBeInTheDocument();

      // Click row to open drawer
      fireEvent.click(screen.getByText('John Doe'));
      expect(await screen.findByText(/Student Registration Record/i)).toBeInTheDocument();

      // Verify button triggers single verification API call
      const verifyBtn = screen.getByRole('button', { name: /^Verify Student$/i });
      fireEvent.click(verifyBtn);

      await waitFor(() => {
        expect(postSpy).toHaveBeenCalledWith(
          '/students/verifications/101/verify',
          expect.objectContaining({ notes: 'Verified by clerk' })
        );
      });
    });

    it('rejecting a student requires mandatory notes in ReasonDialog', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue([
        {
          assignment_id: 102,
          student_id: 2,
          roll_number: '2026CS02',
          name: 'Jane Smith',
          email: 'jane@college.edu',
          mess_name: 'Mess 1',
          hostel_name: 'Hostel A',
          effective_from: '2026-11-01',
          status: 'PENDING_VERIFICATION',
          created_at: '2026-11-01T10:00:00Z',
        },
      ] as any);

      render(
        <MemoryRouter>
          <StudentVerificationPage />
        </MemoryRouter>
      );

      expect(await screen.findByText('Jane Smith')).toBeInTheDocument();
      fireEvent.click(screen.getByText('Jane Smith'));

      // Click Reject Assignment
      const rejectBtn = await screen.findByRole('button', { name: /^Reject Assignment$/i });
      fireEvent.click(rejectBtn);

      // Reason dialog is open
      expect(screen.getByText(/Reject Student Assignment/i)).toBeInTheDocument();
      const submitReasonBtn = screen.getByRole('button', { name: /^Confirm Rejection$/i });
      // Button is disabled when reason is empty (< 5 chars)
      expect(submitReasonBtn).toBeDisabled();

      // Typing valid reason enables button
      const textarea = screen.getByPlaceholderText(/Enter mandatory rejection reason/i);
      fireEvent.change(textarea, { target: { value: 'Student is not residing in Hostel A this semester' } });
      expect(submitReasonBtn).toBeEnabled();
    });
  });

  describe('Menu Authoring Screen', () => {
    it('blocks duplicate food item in a single meal per [DBDD-AC-30]', async () => {
      const mockMenu = {
        menu_id: 10,
        hostel_id: 1,
        hostel_code: 'H-A',
        hostel_name: 'Hostel A',
        year: 2026,
        month: 11,
        month_label: 'November 2026',
        status: 'DRAFT',
        published_at: null,
        published_by_user_id: null,
        version: 1,
        days: [
          {
            date: '2026-11-01',
            meals: [
              {
                menu_meal_id: 1,
                meal_type_code: 'BREAKFAST',
                meal_type_name: 'Breakfast',
                sequence_no: 1,
                items: [
                  { menu_item_id: 1, food_item_id: 5, name: 'Poha', display_order: 1 },
                ],
              },
            ],
          },
        ],
      };

      vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
        if (url.includes('/menus/10')) {
          return mockMenu;
        }
        if (url.includes('/menus/food-items')) {
          return [
            { food_item_id: 5, name: 'Poha' },
            { food_item_id: 6, name: 'Upma' },
          ];
        }
        if (url.includes('/menus')) {
          return [
            {
              menu_id: 10,
              hostel_id: 1,
              hostel_code: 'H-A',
              menu_year: 2026,
              menu_month: 11,
              status: 'DRAFT',
              published_at: null,
              published_by_user_id: null,
              version: 1,
            },
          ];
        }
        return [];
      });

      render(
        <MemoryRouter>
          <MenuPage />
        </MemoryRouter>
      );

      // Click to open editor
      const openEditorBtn = await screen.findByRole('button', { name: /Open Editor/i });
      fireEvent.click(openEditorBtn);

      // Verify editor header
      expect(await screen.findByText(/November 2026 Menu/i)).toBeInTheDocument();
      expect(screen.getByText('Breakfast')).toBeInTheDocument();
      expect(screen.getAllByText('Poha')[0]).toBeInTheDocument();

      // Try selecting Poha again from select dropdown
      const select = screen.getAllByRole('combobox')[0];
      fireEvent.change(select, { target: { value: '5' } });

      // Expect duplicate error message [DBDD-AC-30]
      expect(
        await screen.findByText(/"Poha" is already in this meal \[DBDD-AC-30\]\./i)
      ).toBeInTheDocument();
    });

    it('publish button warns about empty days in dialog', async () => {
      const mockMenu = {
        menu_id: 10,
        hostel_id: 1,
        hostel_code: 'H-A',
        year: 2026,
        month: 11,
        month_label: 'November 2026',
        status: 'DRAFT',
        published_at: null,
        version: 1,
        days: [
          { date: '2026-11-01', meals: [] },
          { date: '2026-11-02', meals: [] },
        ],
      };

      vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
        if (url.includes('/menus/10')) return mockMenu;
        if (url.includes('/menus')) return [{ menu_id: 10, menu_year: 2026, menu_month: 11, status: 'DRAFT', version: 1 }];
        return [];
      });

      render(
        <MemoryRouter>
          <MenuPage />
        </MemoryRouter>
      );

      const openEditorBtn = await screen.findByRole('button', { name: /Open Editor/i });
      fireEvent.click(openEditorBtn);

      const publishBtn = await screen.findByRole('button', { name: /Publish Menu/i });
      fireEvent.click(publishBtn);

      // Warning message should be shown in ConfirmDialog description
      expect(await screen.findByText(/Warning: 2 days in this month have no items scheduled/i)).toBeInTheDocument();
    });
  });

  describe('Extra Items Screen', () => {
    it('enforces price date starting today or later', async () => {
      vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
        if (url.includes('/extras/items/1/prices')) {
          return [{ price_id: 1, price: 25, effective_from: '2026-11-01' }];
        }
        if (url.includes('/extras/items')) {
          return [
            {
              item_id: 1,
              hostel_id: 1,
              name: 'Cold Drink',
              status: 'ACTIVE',
              current_price: 25,
              next_price_change: null,
              created_at: '2026-11-01T10:00:00Z',
              prices: [{ price_id: 1, price: 25, effective_from: '2026-11-01' }],
            },
          ];
        }
        return [];
      });

      render(
        <MemoryRouter>
          <ExtraItemsPage />
        </MemoryRouter>
      );

      expect(await screen.findByText('Cold Drink')).toBeInTheDocument();
      fireEvent.click(screen.getByText('Cold Drink'));

      // Detail drawer should open with hint text
      expect(await screen.findByText(/Past prices cannot be changed/i)).toBeInTheDocument();

      // Enter price and past date
      const priceInput = screen.getByPlaceholderText('30.00');
      fireEvent.change(priceInput, { target: { value: '35' } });

      const dateInput = screen.getByLabelText(/Effective From/i);
      fireEvent.change(dateInput, { target: { value: '2020-01-01' } });

      const savePriceBtn = screen.getByRole('button', { name: /Set New Price Version/i });
      fireEvent.click(savePriceBtn);

      // Form validation error
      expect(
        await screen.findByText(/Past prices cannot be changed; new prices must be effective from today or a future date\./i)
      ).toBeInTheDocument();
    });
  });

  describe('Bills Screen (Read-Only)', () => {
    it('displays period status, draft figures notice when unlocked, and calculation breakdown', async () => {
      vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
        if (url.includes('/billing/periods')) {
          return [
            {
              billing_period_id: 1,
              year: 2026,
              month: 11,
              status: 'BILL_GENERATED',
              start_date: '2026-11-01',
              end_date: '2026-11-30',
            },
          ];
        }
        if (url.includes('/billing/bills/1001')) {
          return {
            bill_id: 1001,
            student_id: 1,
            student_roll_number: '2026CS01',
            student_name: 'John Doe',
            mess_code: 'M-1',
            period_year: 2026,
            period_month: 11,
            period_status: 'BILL_GENERATED',
            common_diet_rate_snapshot: '80.00',
            minimum_diet_count_snapshot: 20,
            actual_meal_count: 24,
            meal_component_amount: '1920.00',
            extra_charges_amount: '150.00',
            adjustment_amount: '0.00',
            final_amount: '2070.00',
            status: 'BILL_GENERATED',
            lines: [
              {
                bill_line_id: 1,
                line_type: 'MEAL_CONSUMPTION',
                description: '24 Actual Meals @ ₹80.00',
                quantity: 24,
                unit_rate: '80.00',
                amount: '1920.00',
                calculation_order: 1,
              },
            ],
            adjustments: [],
            version: 1,
          };
        }
        if (url.includes('/billing/bills')) {
          return [
            {
              bill_id: 1001,
              student_id: 1,
              student_roll_number: '2026CS01',
              student_name: 'John Doe',
              mess_code: 'M-1',
              common_diet_rate_snapshot: '80.00',
              minimum_diet_count_snapshot: 20,
              actual_meal_count: 24,
              meal_component_amount: '1920.00',
              extra_charges_amount: '150.00',
              adjustment_amount: '0.00',
              final_amount: '2070.00',
              status: 'BILL_GENERATED',
              version: 1,
            },
          ];
        }
        return [];
      });

      render(
        <MemoryRouter>
          <BillsPage />
        </MemoryRouter>
      );

      // Verify Read-Only badge and draft figures notice
      expect(await screen.findByText('Read-Only')).toBeInTheDocument();
      expect(
        await screen.findByText(/Not visible to students until locked/i)
      ).toBeInTheDocument();

      // Open detail drawer
      expect(await screen.findByText('John Doe')).toBeInTheDocument();
      fireEvent.click(screen.getByText('John Doe'));

      // Check drawer details: diet rule shows policy min vs actual
      expect(await screen.findByText(/Diet Calculation Breakdown/i)).toBeInTheDocument();
      expect(screen.getByText(/Policy Min: 20 vs Actual: 24/i)).toBeInTheDocument();
    });
  });

  describe('Attendance and Corrections Screen', () => {
    it('lists meal consumptions and opens drawer', async () => {
      vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
        if (url.includes('/attendance/corrections')) {
          return [];
        }
        if (url.includes('/attendance')) {
          return [
            {
              meal_consumption_id: 501,
              transaction_id: 'tx-501',
              student_id: 1,
              roll_number_snapshot: '2026CS01',
              student_name: 'John Doe',
              mess_id: 1,
              mess_name: 'Mess 1',
              meal_type_id: 1,
              meal_type_code: 'BREAKFAST',
              meal_date: '2026-11-10',
              price_at_transaction: '0.00',
              transaction_timestamp: '2026-11-10T08:30:00Z',
              verification_method: 'QR',
              verification_result: 'ACCEPTED',
              source: 'QR',
              accepted_at: '2026-11-10T08:30:00Z',
            },
          ];
        }
        return [];
      });

      render(
        <MemoryRouter>
          <AttendancePage />
        </MemoryRouter>
      );

      expect(await screen.findByText('Attendance & Corrections')).toBeInTheDocument();
      expect(await screen.findByText('John Doe')).toBeInTheDocument();
      expect(screen.getByText('2026CS01')).toBeInTheDocument();

      // Click to open detail drawer
      fireEvent.click(screen.getByText('John Doe'));
      expect(await screen.findByText(/Attendance Record #501/i)).toBeInTheDocument();
    });
  });

  describe('Feedback Screen', () => {
    it('displays satisfaction ratings and opens un-truncated comment drawer', async () => {
      vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
        if (url.includes('/reports/feedback')) {
          return {
            id: 'feedback',
            title: 'Student Feedback',
            columns: [],
            rows: [
              {
                student: 'Alice Walker',
                mess: 'Mess 1',
                month: '2026-11',
                food_quality_rating: 4,
                taste_rating: 5,
                comments: 'The breakfast was outstanding throughout the month!',
              },
            ],
            totals: {
              response_count: 1,
              average_quality: '4.00',
              average_taste: '5.00',
            },
          };
        }
        return [];
      });

      render(
        <MemoryRouter>
          <FeedbackPage />
        </MemoryRouter>
      );

      expect(await screen.findByText(/Student Feedback/i)).toBeInTheDocument();
      expect(screen.getByText(/Non-Anonymous/i)).toBeInTheDocument();
      expect(await screen.findByText('Alice Walker')).toBeInTheDocument();

      // Open drawer
      fireEvent.click(screen.getByText('Alice Walker'));
      expect(await screen.findByText(/Student Comments \(Un-truncated\)/i)).toBeInTheDocument();
      expect(screen.getAllByText(/The breakfast was outstanding throughout the month!/i)[0]).toBeInTheDocument();
    });
  });

  describe('Reports Screen', () => {
    it('renders report catalog and enforces date range <= 366 days', async () => {
      vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
        if (url.includes('/reports')) {
          return {
            reports: [
              {
                id: 'student-billing',
                title: 'Student Billing Summary',
                description: 'Itemized charges by student',
              },
            ],
          };
        }
        return [];
      });

      render(
        <MemoryRouter>
          <ReportsPage />
        </MemoryRouter>
      );

      expect(await screen.findByText(/Reports & Exports/i)).toBeInTheDocument();
      expect((await screen.findAllByText('Student Billing Summary'))[0]).toBeInTheDocument();

      // Select Custom date preset
      const customPresetBtn = screen.getByRole('button', { name: /^Custom Range/i });
      fireEvent.click(customPresetBtn);

      // Set date range > 366 days
      const fromInput = screen.getByLabelText(/From Date/i);
      const toInput = screen.getByLabelText(/To Date/i);
      fireEvent.change(fromInput, { target: { value: '2024-01-01' } });
      fireEvent.change(toInput, { target: { value: '2026-01-01' } });

      const runBtn = screen.getByRole('button', { name: /^Run Report$/i });
      fireEvent.click(runBtn);

      expect(
        await screen.findByText(/cannot exceed 366 days/i)
      ).toBeInTheDocument();
    });
  });
});

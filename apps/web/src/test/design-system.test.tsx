import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { colors, statusMapping, scannerResults } from '../design/tokens';
import {
  Button,
  StatusBadge,
  MoneyText,
  DateText,
  ConfirmDialog,
  ReasonDialog,
  ScanResultOverlay,
} from '../components';

describe('Phase 14 Design Tokens', () => {
  it('enforces exact required color tokens', () => {
    expect(colors.primary).toBe('#0F766E');
    expect(colors.primaryHover).toBe('#115E59');
    expect(colors.primarySubtle).toBe('#F0FDFA');
    expect(colors.primaryBorder).toBe('#99F6E4');
    expect(colors.text).toBe('#0F172A');
    expect(colors.textSecondary).toBe('#475569');
    expect(colors.textMuted).toBe('#64748B');
    expect(colors.bg).toBe('#F8FAFC');
    expect(colors.surface).toBe('#FFFFFF');
    expect(colors.border).toBe('#E2E8F0');
    expect(colors.borderStrong).toBe('#CBD5E1');
    expect(colors.success).toBe('#15803D');
    expect(colors.warning).toBe('#B45309');
    expect(colors.danger).toBe('#B91C1C');
    expect(colors.info).toBe('#1D4ED8');
    expect(colors.neutralState).toBe('#475569');
  });

  it('defines all scanner result screens with exact colors', () => {
    expect(scannerResults.SUCCESS.bg).toBe('#15803D');
    expect(scannerResults.DUPLICATE.bg).toBe('#B45309');
    expect(scannerResults.INVALID_CODE.bg).toBe('#B91C1C');
    expect(scannerResults.UNKNOWN_ROLL.bg).toBe('#B91C1C');
    expect(scannerResults.SUCCESS_PAUSE_NOTICE.bg).toBe('#15803D');
    expect(scannerResults.TIME_INVALID.bg).toBe('#1E293B');
  });

  it('maps all domain statuses accurately', () => {
    expect(statusMapping.syncTransaction.SYNCHRONIZED).toBe('success');
    expect(statusMapping.syncTransaction.CONFLICT).toBe('warning');
    expect(statusMapping.syncTransaction.REJECTED).toBe('danger');
    expect(statusMapping.managerAuthorization.ACTIVE).toBe('success');
    expect(statusMapping.managerAuthorization.SYNC_REQUIRED).toBe('danger');
    expect(statusMapping.trustedTime.VALID).toBe('success');
    expect(statusMapping.pause.SCHEDULED).toBe('info');
    expect(statusMapping.billingPeriod.LOCKED).toBe('success');
    expect(statusMapping.menu.PUBLISHED).toBe('success');
    expect(statusMapping.assignment.PENDING_VERIFICATION).toBe('warning');
  });
});

describe('Formatting Conventions', () => {
  it('formats positive currency with ₹, en-IN grouping, and tabular figures', () => {
    render(<MoneyText amountInRupees={1250000.5} />);
    const el = screen.getByText(/₹12,50,000\.50/);
    expect(el).toBeInTheDocument();
    expect(el).toHaveClass('tabular-nums');
    expect(el).not.toHaveClass('text-danger');
  });

  it('formats negative currency with danger color, minus sign, never parentheses', () => {
    render(<MoneyText amountInRupees={-450.75} />);
    const el = screen.getByText(/-₹450\.75/);
    expect(el).toBeInTheDocument();
    expect(el).toHaveClass('text-danger');
    expect(el.textContent).not.toContain('(');
    expect(el.textContent).not.toContain(')');
  });

  it('formats dates in IST (21 Aug 2026)', () => {
    // 2026-08-21T06:00:00Z -> 11:30 AM IST
    render(<DateText date="2026-08-21T06:00:00Z" />);
    expect(screen.getByText('21 Aug 2026')).toBeInTheDocument();
  });

  it('formats date-times with IST time and tooltip', () => {
    render(<DateText date="2026-08-21T06:12:00Z" includeTime />);
    const el = screen.getByText('21 Aug, 11:42 AM');
    expect(el).toBeInTheDocument();
    expect(el).toHaveAttribute('title', 'Time displayed in Indian Standard Time (IST)');
  });
});

describe('Component Behaviors & Accessibility', () => {
  it('StatusBadge renders word and icon (never color alone)', () => {
    render(<StatusBadge domain="managerAuthorization" status="ACTIVE" />);
    expect(screen.getByText('ACTIVE')).toBeInTheDocument();
    expect(document.querySelector('svg')).toBeInTheDocument();
  });

  it('Button supports variants, loading state, and disabled accessibility', () => {
    const { rerender } = render(<Button variant="primary">Submit</Button>);
    const btn = screen.getByRole('button', { name: 'Submit' });
    expect(btn).not.toBeDisabled();

    rerender(<Button variant="primary" loading>Submit</Button>);
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute('aria-busy', 'true');

    rerender(<Button variant="primary" disabled>Submit</Button>);
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute('aria-disabled', 'true');
  });

  it('ReasonDialog requires minimum length before enabling confirm button', () => {
    const onConfirm = vi.fn();
    const onClose = vi.fn();

    render(
      <ReasonDialog
        isOpen={true}
        onClose={onClose}
        onConfirm={onConfirm}
        title="Administrative Correction"
        description="Provide reason"
        minLength={10}
      />
    );

    const submitBtn = screen.getByRole('button', { name: 'Submit Reason' });
    const textarea = screen.getByLabelText(/Mandatory Reason/);

    expect(submitBtn).toBeDisabled();

    fireEvent.change(textarea, { target: { value: 'Too short' } });
    expect(submitBtn).toBeDisabled();

    fireEvent.change(textarea, { target: { value: 'Student attendance was entered under wrong slot by manager' } });
    expect(submitBtn).not.toBeDisabled();

    fireEvent.click(submitBtn);
    expect(onConfirm).toHaveBeenCalledWith('Student attendance was entered under wrong slot by manager');
  });

  it('ConfirmDialog triggers confirmation callback', () => {
    const onConfirm = vi.fn();
    const onClose = vi.fn();

    render(
      <ConfirmDialog
        isOpen={true}
        onClose={onClose}
        onConfirm={onConfirm}
        title="Confirm Delete"
        description="Are you sure?"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    expect(onConfirm).toHaveBeenCalled();
  });

  it('ScanResultOverlay displays prominent word, icon, and solid background', () => {
    render(
      <ScanResultOverlay
        resultType="SUCCESS"
        studentName="Aarav Sharma"
        rollNumber="2026-CS-001"
      />
    );

    expect(screen.getByText('SUCCESS')).toBeInTheDocument();
    expect(screen.getByText('Aarav Sharma')).toBeInTheDocument();
    expect(screen.getByText('2026-CS-001')).toBeInTheDocument();
  });
});


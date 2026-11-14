import React, { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../../api/client';
import { Card } from '../../components/Card';
import { DataTable, Column } from '../../components/DataTable';
import { Button } from '../../components/Button';
import { Drawer } from '../../components/Drawer';
import { TextField } from '../../components/TextField';
import { Select } from '../../components/Select';
import { Stepper } from '../../components/Stepper';
import { Tabs } from '../../components/Tabs';
import { StatusBadge } from '../../components/StatusBadge';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { ReasonDialog } from '../../components/ReasonDialog';
import { Banner } from '../../components/Banner';
import { Icons } from '../../components/Icons';

interface BillingPeriod {
  billing_period_id: number;
  year: number;
  month: number;
  period_start: string;
  period_end: string;
  status: 'OPEN' | 'BILL_GENERATED' | 'REVIEWED' | 'LOCKED';
  version: number;
  total_billed?: string;
  student_count?: number;
  total_meals?: number;
  total_extras?: string;
  preflight?: {
    ready: boolean;
    missing_rates?: string[];
    missing_policies?: string[];
    stale_extras_count?: number;
    open_conflicts_count?: number;
  };
}

interface BillItem {
  bill_id: number;
  student_id: number;
  student_roll_number: string;
  student_name: string;
  mess_code?: string;
  period_year: number;
  period_month: number;
  meal_charge: string;
  extras_charge: string;
  adjustments_total: string;
  total_amount: string;
  status: string;
  lines?: any[];
}

interface PolicyItem {
  policy_id: number;
  mess_id: number;
  mess_code?: string;
  mess_name?: string;
  min_diet_count: number;
  effective_from: string;
  effective_to?: string;
}

interface SemesterItem {
  semester_id: number;
  code: string;
  name: string;
  start_date: string;
  end_date: string;
}

export const BillingPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'periods' | 'policies' | 'semesters'>('periods');
  const [periods, setPeriods] = useState<BillingPeriod[]>([]);
  const [selectedPeriod, setSelectedPeriod] = useState<BillingPeriod | null>(null);
  const [bills, setBills] = useState<BillItem[]>([]);
  const [billsLoading, setBillsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Bill detail drawer
  const [selectedBill, setSelectedBill] = useState<BillItem | null>(null);

  // Action state (Generate, Review, Lock, Unlock)
  const [actionLoading, setActionLoading] = useState(false);
  const [lockConfirmOpen, setLockConfirmOpen] = useState(false);
  const [unlockReasonOpen, setUnlockReasonOpen] = useState(false);

  // Adjustment state (Fee / Fine only - C01)
  const [adjustingBill, setAdjustingBill] = useState<BillItem | null>(null);
  const [adjustmentType, setAdjustmentType] = useState<'FEE' | 'FINE'>('FEE');
  const [adjustmentAmount, setAdjustmentAmount] = useState('');
  const [adjustmentReason, setAdjustmentReason] = useState('');
  const [adjustmentSubmitting, setAdjustmentSubmitting] = useState(false);
  const [adjustmentError, setAdjustmentError] = useState<string | null>(null);

  // Policies Tab state
  const [policies, setPolicies] = useState<PolicyItem[]>([]);
  const [policyMessId, setPolicyMessId] = useState('');
  const [policyMinDiet, setPolicyMinDiet] = useState('20');
  const [policyEffectiveFrom, setPolicyEffectiveFrom] = useState('');
  const [policyDrawerOpen, setPolicyDrawerOpen] = useState(false);

  // Semesters & Balances Tab state
  const [semesters, setSemesters] = useState<SemesterItem[]>([]);
  const [balances, setBalances] = useState<any[]>([]);
  const [creditStudentId, setCreditStudentId] = useState('');
  const [creditAmount, setCreditAmount] = useState('');
  const [creditRef, setCreditRef] = useState('');
  const [creditDrawerOpen, setCreditDrawerOpen] = useState(false);
  const [creditSubmitting, setCreditSubmitting] = useState(false);

  const fetchPeriods = useCallback(async () => {
    setError(null);
    try {
      const res = await apiClient.get<any>('/billing/periods');
      const list: BillingPeriod[] = Array.isArray(res) ? res : res?.results || [];
      setPeriods(list);

      if (list.length > 0) {
        // Pick first or keep selected
        const currentId = selectedPeriod?.billing_period_id || list[0].billing_period_id;
        const detail = await apiClient.get<BillingPeriod>(`/billing/periods/${currentId}`);
        setSelectedPeriod(detail);
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to load billing periods.');
    }
  }, [selectedPeriod?.billing_period_id]);

  useEffect(() => {
    fetchPeriods();
  }, [fetchPeriods]);

  // Fetch bills when selected period changes
  const fetchBillsForPeriod = useCallback(async (periodId: number) => {
    setBillsLoading(true);
    try {
      const res = await apiClient.get<any>(`/billing/bills?period_id=${periodId}`);
      const list = Array.isArray(res) ? res : res?.results || [];
      setBills(list);
    } catch {
      setBills([]);
    } finally {
      setBillsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedPeriod?.billing_period_id) {
      fetchBillsForPeriod(selectedPeriod.billing_period_id);
    }
  }, [selectedPeriod?.billing_period_id, fetchBillsForPeriod]);

  // Tab change fetchers
  useEffect(() => {
    if (activeTab === 'policies') {
      (async () => {
        try {
          const res = await apiClient.get<any>('/billing/policies');
          setPolicies(Array.isArray(res) ? res : res?.results || []);
        } catch {}
      })();
    } else if (activeTab === 'semesters') {
      (async () => {
        try {
          const [sRes, bRes] = await Promise.all([
            apiClient.get<any>('/billing/semesters'),
            apiClient.get<any>('/billing/balances').catch(() => ({ results: [] })),
          ]);
          setSemesters(Array.isArray(sRes) ? sRes : sRes?.results || []);
          setBalances(Array.isArray(bRes) ? bRes : bRes?.results || []);
        } catch {}
      })();
    }
  }, [activeTab]);

  // Stepper mapping
  const getStepperIndex = (status: BillingPeriod['status']): number => {
    switch (status) {
      case 'OPEN':
        return 0;
      case 'BILL_GENERATED':
        return 1;
      case 'REVIEWED':
        return 2;
      case 'LOCKED':
        return 3;
      default:
        return 0;
    }
  };

  // Actions
  const handleGenerate = async () => {
    if (!selectedPeriod) return;
    setActionLoading(true);
    try {
      await apiClient.post(`/billing/periods/${selectedPeriod.billing_period_id}/generate`, {});
      setSuccessMsg('Billing run executed. Bills generated for all active allocations.');
      const detail = await apiClient.get<BillingPeriod>(`/billing/periods/${selectedPeriod.billing_period_id}`);
      setSelectedPeriod(detail);
      fetchBillsForPeriod(selectedPeriod.billing_period_id);
      fetchPeriods();
    } catch (err: any) {
      setError(err?.message || 'Failed to generate bills.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleReview = async () => {
    if (!selectedPeriod) return;
    setActionLoading(true);
    try {
      await apiClient.post(`/billing/periods/${selectedPeriod.billing_period_id}/review`, {});
      setSuccessMsg('Billing period marked as REVIEWED. Ready for locking.');
      const detail = await apiClient.get<BillingPeriod>(`/billing/periods/${selectedPeriod.billing_period_id}`);
      setSelectedPeriod(detail);
      fetchPeriods();
    } catch (err: any) {
      setError(err?.message || 'Failed to mark period as reviewed.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleLock = async () => {
    if (!selectedPeriod) return;
    setActionLoading(true);
    try {
      await apiClient.post(`/billing/periods/${selectedPeriod.billing_period_id}/lock`, {});
      setSuccessMsg('Billing period LOCKED. Ledger charges posted and bills finalized.');
      setLockConfirmOpen(false);
      const detail = await apiClient.get<BillingPeriod>(`/billing/periods/${selectedPeriod.billing_period_id}`);
      setSelectedPeriod(detail);
      fetchPeriods();
    } catch (err: any) {
      setError(err?.message || 'Failed to lock billing period.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleUnlock = async (reason: string) => {
    if (!selectedPeriod) return;
    setActionLoading(true);
    try {
      await apiClient.post(`/billing/periods/${selectedPeriod.billing_period_id}/unlock`, {
        reason: reason,
      });
      setSuccessMsg('Billing period UNLOCKED. Ledger charges reversed and bills reopened.');
      setUnlockReasonOpen(false);
      const detail = await apiClient.get<BillingPeriod>(`/billing/periods/${selectedPeriod.billing_period_id}`);
      setSelectedPeriod(detail);
      fetchPeriods();
    } catch (err: any) {
      setError(err?.message || 'Failed to unlock billing period.');
    } finally {
      setActionLoading(false);
    }
  };

  // Adjustment (C01: Positive amount, FEE or FINE, mandatory reason)
  const handleAddAdjustment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!adjustingBill) return;
    setAdjustmentError(null);

    const amt = parseFloat(adjustmentAmount);
    if (isNaN(amt) || amt <= 0) {
      setAdjustmentError('Adjustment amount must be a positive number (C01: no discounts or negative values).');
      return;
    }
    if (!adjustmentReason.trim()) {
      setAdjustmentError('Mandatory administrative reason is required.');
      return;
    }

    setAdjustmentSubmitting(true);
    try {
      await apiClient.post(`/billing/bills/${adjustingBill.bill_id}/adjustments`, {
        adjustment_type: adjustmentType,
        amount: amt,
        reason: adjustmentReason.trim(),
      });
      setSuccessMsg(`Adjustment (${adjustmentType}: ₹${amt}) added to bill #${adjustingBill.bill_id}.`);
      setAdjustingBill(null);
      if (selectedPeriod) fetchBillsForPeriod(selectedPeriod.billing_period_id);
    } catch (err: any) {
      setAdjustmentError(err?.message || 'Failed to add adjustment.');
    } finally {
      setAdjustmentSubmitting(false);
    }
  };

  // Add Credit to Student Balance
  const handleAddCredit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!creditStudentId || !creditAmount) return;
    setCreditSubmitting(true);
    try {
      await apiClient.post(`/billing/balances/${creditStudentId}/credits`, {
        amount: parseFloat(creditAmount),
        reference_number: creditRef || `REF-${Date.now()}`,
        notes: 'Super Admin balance credit',
      });
      setSuccessMsg(`Credit of ₹${creditAmount} applied to student account.`);
      setCreditDrawerOpen(false);
      const bRes = await apiClient.get<any>('/billing/balances');
      setBalances(Array.isArray(bRes) ? bRes : bRes?.results || []);
    } catch (err: any) {
      setError(err?.message || 'Failed to add balance credit.');
    } finally {
      setCreditSubmitting(false);
    }
  };

  const billColumns: Column<BillItem>[] = [
    {
      key: 'student',
      header: 'Student',
      render: (row) => (
        <div>
          <span className="font-mono font-bold text-text">{row.student_roll_number}</span>
          <div className="text-[12px] text-text-muted">{row.student_name}</div>
        </div>
      ),
    },
    {
      key: 'meal_charge',
      header: 'Meals',
      render: (row) => <span>₹{parseFloat(row.meal_charge || '0').toFixed(2)}</span>,
    },
    {
      key: 'extras_charge',
      header: 'Extras',
      render: (row) => <span>₹{parseFloat(row.extras_charge || '0').toFixed(2)}</span>,
    },
    {
      key: 'adjustments_total',
      header: 'Adjustments (C01)',
      render: (row) => (
        <span className={parseFloat(row.adjustments_total || '0') > 0 ? 'text-danger font-medium' : ''}>
          ₹{parseFloat(row.adjustments_total || '0').toFixed(2)}
        </span>
      ),
    },
    {
      key: 'total_amount',
      header: 'Total Billed',
      render: (row) => (
        <span className="font-bold text-text">₹{parseFloat(row.total_amount || '0').toFixed(2)}</span>
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'right',
      render: (row) => (
        <div className="flex items-center justify-end gap-2" onClick={(e) => e.stopPropagation()}>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setSelectedBill(row)}
            icon={<Icons.FileText className="w-3.5 h-3.5" />}
          >
            Lines
          </Button>

          {/* Locked bills show no edit controls [SPEC DBDD §8] */}
          {selectedPeriod?.status !== 'LOCKED' && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                setAdjustingBill(row);
                setAdjustmentAmount('');
                setAdjustmentReason('');
                setAdjustmentError(null);
              }}
              icon={<Icons.Plus className="w-3.5 h-3.5" />}
            >
              Adjust
            </Button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-5">
        <div>
          <h1 className="text-[22px] font-bold text-text">Billing & Prepaid Balances</h1>
          <p className="text-[13px] text-text-secondary mt-0.5">
            Monthly billing cycles, pre-flight checks, adjustment audits (C01), and student balances
          </p>
        </div>
      </div>

      {successMsg && (
        <Banner variant="success" onClose={() => setSuccessMsg(null)}>
          {successMsg}
        </Banner>
      )}

      {error && (
        <Banner variant="danger" onClose={() => setError(null)}>
          {error}
        </Banner>
      )}

      <Tabs
        activeKey={activeTab}
        onChange={(k) => setActiveTab(k as any)}
        items={[
          { key: 'periods', label: 'Billing Periods & Cycles' },
          { key: 'policies', label: 'Minimum Diet Policies' },
          { key: 'semesters', label: 'Semesters & Balances' },
        ]}
      />

      {/* TAB 1: Billing Periods */}
      {activeTab === 'periods' && selectedPeriod && (
        <div className="space-y-6">
          {/* Stepper Card with Legal Next Action Button and Period Selector */}
          <Card>
            <div className="space-y-5">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div className="flex items-center gap-4">
                  {periods.length > 1 && (
                    <div className="w-56">
                      <Select
                        label="Select Billing Period"
                        value={selectedPeriod.billing_period_id.toString()}
                        onChange={async (e) => {
                          const pId = parseInt(e.target.value);
                          const detail = await apiClient.get<BillingPeriod>(`/billing/periods/${pId}`);
                          setSelectedPeriod(detail);
                          fetchBillsForPeriod(pId);
                        }}
                        options={periods.map((p) => ({
                          value: p.billing_period_id.toString(),
                          label: `${p.year}-${String(p.month).padStart(2, '0')} (${p.status})`,
                        }))}
                      />
                    </div>
                  )}
                  <div>
                    <h3 className="text-[16px] font-bold text-text">
                      Period: {selectedPeriod.year} - {String(selectedPeriod.month).padStart(2, '0')}
                    </h3>
                    <p className="text-[12px] text-text-muted mt-0.5">
                      Range: {selectedPeriod.period_start} to {selectedPeriod.period_end}
                    </p>
                  </div>
                </div>

                {/* Only the legal next action as the primary button */}
                <div className="flex items-center gap-3">
                  {selectedPeriod.status === 'OPEN' && (
                    <Button
                      variant="primary"
                      onClick={handleGenerate}
                      loading={actionLoading}
                      icon={<Icons.Play className="w-4 h-4" />}
                    >
                      Generate Bills
                    </Button>
                  )}

                  {selectedPeriod.status === 'BILL_GENERATED' && (
                    <>
                      <Button
                        variant="secondary"
                        onClick={handleGenerate}
                        loading={actionLoading}
                        icon={<Icons.RefreshCw className="w-4 h-4" />}
                      >
                        Regenerate
                      </Button>
                      <Button
                        variant="primary"
                        onClick={handleReview}
                        loading={actionLoading}
                        icon={<Icons.Check className="w-4 h-4" />}
                      >
                        Mark Reviewed
                      </Button>
                    </>
                  )}

                  {selectedPeriod.status === 'REVIEWED' && (
                    <Button
                      variant="primary"
                      onClick={() => setLockConfirmOpen(true)}
                      loading={actionLoading}
                      icon={<Icons.Lock className="w-4 h-4" />}
                    >
                      Lock Period
                    </Button>
                  )}

                  {selectedPeriod.status === 'LOCKED' && (
                    <Button
                      variant="ghost"
                      className="text-danger hover:bg-danger-subtle"
                      onClick={() => setUnlockReasonOpen(true)}
                      loading={actionLoading}
                      icon={<Icons.Unlock className="w-4 h-4" />}
                    >
                      Unlock Period
                    </Button>
                  )}
                </div>
              </div>

              {/* Progress Stepper */}
              <Stepper
                steps={[
                  { id: 'open', label: '1. Open' },
                  { id: 'generated', label: '2. Bill Generated' },
                  { id: 'reviewed', label: '3. Reviewed' },
                  { id: 'locked', label: '4. Locked' },
                ]}
                currentStep={getStepperIndex(selectedPeriod.status)}
              />
            </div>
          </Card>

          {/* Stat Tiles & Pre-Flight Checklist */}
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
            <div className="p-4 bg-surface border border-border rounded-[10px]">
              <span className="text-[12px] text-text-muted">Total Billed</span>
              <div className="text-[20px] font-bold text-text mt-1">
                ₹{parseFloat(selectedPeriod.total_billed || '0').toFixed(2)}
              </div>
            </div>
            <div className="p-4 bg-surface border border-border rounded-[10px]">
              <span className="text-[12px] text-text-muted">Billed Students</span>
              <div className="text-[20px] font-bold text-text mt-1">
                {selectedPeriod.student_count ?? bills.length}
              </div>
            </div>
            <div className="p-4 bg-surface border border-border rounded-[10px]">
              <span className="text-[12px] text-text-muted">Total Meals Count</span>
              <div className="text-[20px] font-bold text-text mt-1">
                {selectedPeriod.total_meals ?? 0}
              </div>
            </div>
            <div className="p-4 bg-surface border border-border rounded-[10px]">
              <span className="text-[12px] text-text-muted">Period Status</span>
              <div className="mt-1">
                <StatusBadge domain="billingPeriod" status={selectedPeriod.status} />
              </div>
            </div>
          </div>

          {/* Pre-Flight Checklist Card */}
          {selectedPeriod.status === 'OPEN' && selectedPeriod.preflight && (
            <Card title="Pre-Flight Generation Checklist" subtitle="Automated validation before billing calculation">
              <div className="space-y-2 text-[13px]">
                <div className="flex items-center gap-2">
                  {selectedPeriod.preflight.missing_rates && selectedPeriod.preflight.missing_rates.length > 0 ? (
                    <>
                      <Icons.XCircle className="w-4 h-4 text-danger flex-shrink-0" />
                      <span className="text-danger">
                        Missing Meal Rates for mess facilities: {selectedPeriod.preflight.missing_rates.join(', ')} (blocks generation)
                      </span>
                    </>
                  ) : (
                    <>
                      <Icons.CheckCircle className="w-4 h-4 text-success flex-shrink-0" />
                      <span className="text-success font-medium">All mess facilities have active meal rates</span>
                    </>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  {selectedPeriod.preflight.open_conflicts_count && selectedPeriod.preflight.open_conflicts_count > 0 ? (
                    <>
                      <Icons.AlertTriangle className="w-4 h-4 text-warning flex-shrink-0" />
                      <span className="text-warning-text">
                        Warning: {selectedPeriod.preflight.open_conflicts_count} open sync conflicts dated in this period.
                      </span>
                    </>
                  ) : (
                    <>
                      <Icons.CheckCircle className="w-4 h-4 text-success flex-shrink-0" />
                      <span className="text-success font-medium">Zero open sync conflicts in this period</span>
                    </>
                  )}
                </div>
              </div>
            </Card>
          )}

          {/* Bills Table */}
          <Card
            title={`Period Bills (${bills.length})`}
            subtitle={selectedPeriod.status === 'LOCKED' ? 'Locked bills (read-only, no edit controls DBDD §8)' : 'Review student charges and apply audited fee/fine adjustments'}
          >
            <DataTable
              columns={billColumns}
              data={bills}
              loading={billsLoading}
              keyExtractor={(b) => b.bill_id.toString()}
              emptyMessage="No bills generated for this period yet. Click 'Generate Bills' to begin."
            />
          </Card>
        </div>
      )}

      {/* TAB 2: Policies */}
      {activeTab === 'policies' && (
        <Card
          title="Minimum Diet Policies"
          subtitle="Minimum diet meal count requirements per mess facility"
          actions={
            <Button
              size="sm"
              variant="primary"
              onClick={() => {
                setPolicyMessId('');
                setPolicyMinDiet('20');
                setPolicyEffectiveFrom(new Date().toISOString().split('T')[0]);
                setPolicyDrawerOpen(true);
              }}
              icon={<Icons.Plus className="w-3.5 h-3.5" />}
            >
              Add Policy
            </Button>
          }
        >
          <div className="space-y-4">
            <DataTable
              columns={[
                {
                  key: 'mess_code',
                  header: 'Mess Hall',
                  render: (p: PolicyItem) => <span className="font-semibold">{p.mess_name || p.mess_code}</span>,
                },
                {
                  key: 'min_diet_count',
                  header: 'Minimum Diet Count',
                  render: (p: PolicyItem) => <span className="font-bold">{p.min_diet_count} meals</span>,
                },
                {
                  key: 'effective_from',
                  header: 'Effective Date',
                  render: (p: PolicyItem) => <span>{p.effective_from}</span>,
                },
              ]}
              data={policies}
              keyExtractor={(p) => p.policy_id.toString()}
              emptyMessage="No policies configured."
            />
          </div>
        </Card>
      )}

      {/* TAB 3: Semesters & Balances */}
      {activeTab === 'semesters' && (
        <div className="space-y-6">
          {semesters.length > 0 && (
            <Card title="Active Semesters">
              <DataTable
                columns={[
                  { key: 'code', header: 'Semester Code', render: (s: SemesterItem) => <span className="font-mono font-bold">{s.code}</span> },
                  { key: 'name', header: 'Semester Name', render: (s: SemesterItem) => <span>{s.name}</span> },
                  { key: 'dates', header: 'Date Range', render: (s: SemesterItem) => <span>{s.start_date} to {s.end_date}</span> },
                ]}
                data={semesters}
                keyExtractor={(s) => s.semester_id.toString()}
              />
            </Card>
          )}

          <div className="flex items-center justify-between">
            <h3 className="text-[16px] font-bold text-text">Student Prepaid Balances</h3>
            <Button
              variant="primary"
              onClick={() => {
                setCreditStudentId('');
                setCreditAmount('');
                setCreditRef('');
                setCreditDrawerOpen(true);
              }}
              icon={<Icons.Plus className="w-4 h-4" />}
            >
              Add Balance Credit
            </Button>
          </div>

          <Card title="Account Balances & Ledgers">
            <DataTable
              columns={[
                {
                  key: 'student',
                  header: 'Student',
                  render: (b: any) => (
                    <div>
                      <div className="font-mono font-bold text-text">{b.roll_number}</div>
                      <div className="text-[12px] text-text-muted">{b.full_name}</div>
                    </div>
                  ),
                },
                {
                  key: 'balance',
                  header: 'Current Prepaid Balance',
                  render: (b: any) => (
                    <span className="font-bold text-text">
                      ₹{parseFloat(b.current_balance || '0').toFixed(2)}
                    </span>
                  ),
                },
              ]}
              data={balances}
              keyExtractor={(b) => b.balance_id?.toString() || b.student_id?.toString()}
              emptyMessage="No student balances found."
            />
          </Card>
        </div>
      )}

      {/* Bill Lines Drawer */}
      <Drawer
        isOpen={Boolean(selectedBill)}
        onClose={() => setSelectedBill(null)}
        title={selectedBill ? `Bill Breakdown: ${selectedBill.student_roll_number}` : 'Bill Details'}
        subtitle={`Period: ${selectedBill?.period_year}-${selectedBill?.period_month}`}
        width="max-w-md"
        footer={
          <div className="flex justify-end w-full">
            <Button variant="secondary" onClick={() => setSelectedBill(null)}>
              Close
            </Button>
          </div>
        }
      >
        {selectedBill && (
          <div className="space-y-4 text-[13px]">
            <div className="p-4 bg-bg border border-border rounded-[10px] space-y-2">
              <div className="flex justify-between">
                <span className="text-text-muted">Meal Charges:</span>
                <span className="font-medium text-text">₹{parseFloat(selectedBill.meal_charge).toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">Hostel Extras:</span>
                <span className="font-medium text-text">₹{parseFloat(selectedBill.extras_charge).toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">Adjustments (C01):</span>
                <span className="font-medium text-danger">₹{parseFloat(selectedBill.adjustments_total).toFixed(2)}</span>
              </div>
              <div className="pt-2 border-t border-border flex justify-between font-bold text-[15px]">
                <span className="text-text">Total Amount:</span>
                <span className="text-primary">₹{parseFloat(selectedBill.total_amount).toFixed(2)}</span>
              </div>
            </div>
          </div>
        )}
      </Drawer>

      {/* Add Adjustment Drawer (C01 Rules) */}
      <Drawer
        isOpen={Boolean(adjustingBill)}
        onClose={() => setAdjustingBill(null)}
        title={`Add Adjustment: ${adjustingBill?.student_roll_number}`}
        subtitle="Constraint C01: Add fee/fine uses a positive amount and mandatory reason. No discounts or credit options."
        width="max-w-md"
        footer={
          <div className="flex items-center justify-end gap-3 w-full">
            <Button variant="secondary" onClick={() => setAdjustingBill(null)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={handleAddAdjustment} loading={adjustmentSubmitting}>
              Apply Adjustment
            </Button>
          </div>
        }
      >
        <form onSubmit={handleAddAdjustment} className="space-y-4">
          {adjustmentError && (
            <Banner variant="danger" className="text-[13px]">
              {adjustmentError}
            </Banner>
          )}

          <div className="p-3 bg-bg border border-border rounded text-[12px] text-text-secondary">
            <strong>Rule C01:</strong> Only positive FEE or FINE adjustments are permitted on individual bills.
          </div>

          <Select
            label="Adjustment Type"
            value={adjustmentType}
            onChange={(e) => setAdjustmentType(e.target.value as 'FEE' | 'FINE')}
            options={[
              { value: 'FEE', label: 'FEE (Administrative / Late Fee)' },
              { value: 'FINE', label: 'FINE (Disciplinary / Food Waste Fine)' },
            ]}
          />

          <TextField
            label="Amount (₹) — Must be positive"
            type="number"
            step="0.01"
            min="0.01"
            required
            value={adjustmentAmount}
            onChange={(e) => setAdjustmentAmount(e.target.value)}
            placeholder="e.g. 250.00"
          />

          <TextField
            label="Mandatory Reason"
            required
            value={adjustmentReason}
            onChange={(e) => setAdjustmentReason(e.target.value)}
            placeholder="e.g. Late hostel documentation fee"
          />
        </form>
      </Drawer>

      {/* Lock Confirmation Dialog */}
      <ConfirmDialog
        isOpen={lockConfirmOpen}
        onClose={() => setLockConfirmOpen(false)}
        onConfirm={handleLock}
        title="Lock Billing Period"
        description={
          selectedPeriod ? (
            <div className="space-y-2">
              <p>Are you sure you want to lock this billing period? Locking is an immutable financial event.</p>
              <div className="p-3 bg-bg border border-border rounded text-[13px] font-semibold">
                Total Billed: ₹{parseFloat(selectedPeriod.total_billed || '0').toFixed(2)} • Students: {selectedPeriod.student_count ?? bills.length}
              </div>
              <p className="text-[12px] text-text-secondary">
                Once locked, student bills become visible to students, ledger debits post to student prepaid accounts, and bills show no edit controls.
              </p>
            </div>
          ) : ''
        }
        confirmLabel="Confirm Lock"
        loading={actionLoading}
      />

      {/* Unlock ReasonDialog */}
      <ReasonDialog
        isOpen={unlockReasonOpen}
        onClose={() => setUnlockReasonOpen(false)}
        onConfirm={handleUnlock}
        title="Unlock Billing Period"
        description="Unlocking reopens bills, reverses all ledger charges posted for this cycle, and hides finalized bills from students. A mandatory audit reason is required."
        confirmLabel="Unlock Period"
        variant="danger"
        loading={actionLoading}
      />

      {/* Add Balance Credit Drawer */}
      <Drawer
        isOpen={creditDrawerOpen}
        onClose={() => setCreditDrawerOpen(false)}
        title="Add Prepaid Account Credit"
        subtitle="Post a credit deposit to a student's prepaid dining account"
        width="max-w-md"
        footer={
          <div className="flex items-center justify-end gap-3 w-full">
            <Button variant="secondary" onClick={() => setCreditDrawerOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={handleAddCredit} loading={creditSubmitting}>
              Apply Credit
            </Button>
          </div>
        }
      >
        <form onSubmit={handleAddCredit} className="space-y-4">
          <TextField
            label="Student ID"
            required
            value={creditStudentId}
            onChange={(e) => setCreditStudentId(e.target.value)}
            placeholder="e.g. 1"
          />
          <TextField
            label="Credit Amount (₹)"
            type="number"
            step="0.01"
            min="0.01"
            required
            value={creditAmount}
            onChange={(e) => setCreditAmount(e.target.value)}
            placeholder="e.g. 5000.00"
          />
          <TextField
            label="Reference Number / Receipt"
            value={creditRef}
            onChange={(e) => setCreditRef(e.target.value)}
            placeholder="e.g. BANK-REC-9982"
          />
        </form>
      </Drawer>

      {/* Add Policy Drawer */}
      <Drawer
        isOpen={policyDrawerOpen}
        onClose={() => setPolicyDrawerOpen(false)}
        title="Add Minimum Diet Policy"
        subtitle="Configure the minimum billable diet count per semester for a mess"
        width="max-w-md"
        footer={
          <div className="flex items-center justify-end gap-3 w-full">
            <Button variant="secondary" onClick={() => setPolicyDrawerOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={async () => {
                try {
                  await apiClient.post('/billing/policies', {
                    mess_id: parseInt(policyMessId) || 1,
                    min_diet_count: parseInt(policyMinDiet) || 20,
                    effective_from: policyEffectiveFrom,
                  });
                  setSuccessMsg('Minimum diet policy saved.');
                  setPolicyDrawerOpen(false);
                  const res = await apiClient.get<any>('/billing/policies');
                  setPolicies(Array.isArray(res) ? res : res?.results || []);
                } catch (err: any) {
                  setError(err?.message || 'Failed to save policy.');
                }
              }}
            >
              Save Policy
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <TextField
            label="Mess Facility ID"
            required
            value={policyMessId}
            onChange={(e) => setPolicyMessId(e.target.value)}
            placeholder="e.g. 1"
          />
          <TextField
            label="Minimum Diet Count (Meals)"
            type="number"
            required
            value={policyMinDiet}
            onChange={(e) => setPolicyMinDiet(e.target.value)}
          />
          <TextField
            label="Effective From Date"
            type="date"
            required
            value={policyEffectiveFrom}
            onChange={(e) => setPolicyEffectiveFrom(e.target.value)}
          />
        </div>
      </Drawer>
    </div>
  );
};

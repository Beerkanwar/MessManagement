import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Card } from '../../components/Card';
import { Button } from '../../components/Button';
import { StatusBadge } from '../../components/StatusBadge';
import { Skeleton } from '../../components/Skeleton';
import { EmptyState } from '../../components/EmptyState';
import { ErrorState } from '../../components/ErrorState';
import { Drawer } from '../../components/Drawer';
import { MoneyText } from '../../components/MoneyText';
import { Icons } from '../../components/Icons';
import { apiClient } from '../../api/client';
import { useAuth } from '../../state/auth';
import { cn } from '../../lib/utils';

export interface BillingPeriod {
  billing_period_id: number;
  year: number;
  month: number;
  status: 'OPEN' | 'BILL_GENERATED' | 'REVIEWED' | 'LOCKED';
  start_date: string;
  end_date: string;
  is_locked?: boolean;
}

export interface BillLine {
  bill_line_id: number;
  line_type: 'MINIMUM_DIET' | 'MEAL_CONSUMPTION' | 'EXTRA_CONSUMPTION' | string;
  source_entity_type?: string;
  source_entity_id?: number;
  description: string;
  quantity: number | string;
  unit_rate: number | string;
  amount: number | string;
  calculation_order: number;
}

export interface BillAdjustment {
  adjustment_id: number;
  amount: number | string;
  adjustment_type: 'FEE' | 'FINE' | string;
  reason: string;
  created_by?: number;
  created_by_name?: string;
  created_at?: string;
}

export interface BillItem {
  bill_id: number;
  student_id: number;
  student_roll_number: string;
  student_name: string;
  hostel_id: number;
  mess_id: number;
  mess_code: string;
  billing_period_id: number;
  period_year: number;
  period_month: number;
  period_status: string;
  semester_id?: number;
  semester_code?: string;
  meal_component_amount: string | number;
  extra_charges_amount: string | number;
  adjustment_amount: string | number;
  final_amount: string | number;
  common_diet_rate_snapshot: string | number;
  minimum_diet_count_snapshot: number;
  actual_meal_count: number;
  status: string;
  generated_at?: string;
  locked_at?: string;
  lines?: BillLine[];
  adjustments?: BillAdjustment[];
  version: number;
}

export const BillsPage: React.FC = () => {
  const { assignment } = useAuth();

  // Periods
  const [periods, setPeriods] = useState<BillingPeriod[]>([]);
  const [selectedPeriodId, setSelectedPeriodId] = useState<number | null>(null);
  const [loadingPeriods, setLoadingPeriods] = useState(true);

  // Bills in selected period
  const [bills, setBills] = useState<BillItem[]>([]);
  const [loadingBills, setLoadingBills] = useState(false);
  const [billsError, setBillsError] = useState<{ code: string; message: string; traceId?: string } | null>(null);

  // Search & Filter
  const [searchQuery, setSearchQuery] = useState('');

  // Selected Bill for Detail Drawer
  const [selectedBill, setSelectedBill] = useState<BillItem | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Fetch Periods
  const fetchPeriods = useCallback(async () => {
    setLoadingPeriods(true);
    try {
      const res = await apiClient.get<any>('/api/v1/billing/periods');
      const items = res.results || res;
      const periodList: BillingPeriod[] = Array.isArray(items) ? items : [];
      setPeriods(periodList);
      if (periodList.length > 0 && selectedPeriodId === null) {
        setSelectedPeriodId(periodList[0].billing_period_id);
      }
    } catch (err: any) {
      console.error('Failed to load billing periods', err);
    } finally {
      setLoadingPeriods(false);
    }
  }, [selectedPeriodId]);

  // Fetch Bills for selected period
  const fetchBills = useCallback(async (periodId: number) => {
    setLoadingBills(true);
    setBillsError(null);
    try {
      const res = await apiClient.get<any>(`/api/v1/billing/bills?billing_period_id=${periodId}`);
      const items = res.results || res;
      setBills(Array.isArray(items) ? items : []);
    } catch (err: any) {
      setBillsError({
        code: err.code || 'LOAD_FAILED',
        message: err.message || 'Failed to load student bills for this period',
        traceId: err.trace_id,
      });
    } finally {
      setLoadingBills(false);
    }
  }, []);

  useEffect(() => {
    fetchPeriods();
  }, [fetchPeriods]);

  useEffect(() => {
    if (selectedPeriodId !== null) {
      fetchBills(selectedPeriodId);
    }
  }, [selectedPeriodId, fetchBills]);

  // Load single bill detail with calculation lines
  const openBillDetail = async (bill: BillItem) => {
    setSelectedBill(bill);
    setLoadingDetail(true);
    try {
      const fullBill = await apiClient.get<BillItem>(`/api/v1/billing/bills/${bill.bill_id}`);
      setSelectedBill(fullBill);
    } catch (err) {
      console.error('Failed to load bill detail breakdown', err);
    } finally {
      setLoadingDetail(false);
    }
  };

  const activePeriod = periods.find((p) => p.billing_period_id === selectedPeriodId);
  const isPeriodUnlocked = activePeriod?.status !== 'LOCKED';

  // Filter bills
  const filteredBills = useMemo(() => {
    if (!searchQuery.trim()) return bills;
    const q = searchQuery.toLowerCase();
    return bills.filter(
      (b) =>
        b.student_name?.toLowerCase().includes(q) ||
        b.student_roll_number?.toLowerCase().includes(q) ||
        b.mess_code?.toLowerCase().includes(q)
    );
  }, [bills, searchQuery]);

  // Summary totals
  const totals = useMemo(() => {
    return filteredBills.reduce(
      (acc, b) => {
        acc.studentsCount += 1;
        acc.totalBilled += Number(b.final_amount) || 0;
        acc.extrasTotal += Number(b.extra_charges_amount) || 0;
        acc.feesFinesTotal += Number(b.adjustment_amount) || 0;
        return acc;
      },
      { studentsCount: 0, totalBilled: 0, extrasTotal: 0, feesFinesTotal: 0 }
    );
  }, [filteredBills]);

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-text-primary">Student Bills</h1>
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-surface-subtle border border-border-default text-text-secondary">
              Read-Only
            </span>
          </div>
          <p className="text-sm text-text-secondary mt-1">
            Inspect monthly diet and extras charges for{' '}
            <span className="font-semibold text-text-primary">
              {assignment?.hostel_name || (assignment?.hostel_id ? `Hostel ${assignment.hostel_id}` : 'your hostel')}
            </span>
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Link to="/clerk/reports">
            <Button variant="secondary" size="sm" icon={<Icons.Calendar className="w-4 h-4" />}>
              Export via Reports
            </Button>
          </Link>
        </div>
      </div>

      {/* Period Selector & Notice Banner */}
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-bold text-text-secondary uppercase tracking-wider mr-2">
            Billing Period:
          </span>
          {loadingPeriods ? (
            <Skeleton className="h-8 w-64" />
          ) : periods.length === 0 ? (
            <span className="text-xs text-text-muted">No billing periods configured</span>
          ) : (
            periods.map((p) => {
              const isSelected = p.billing_period_id === selectedPeriodId;
              const periodLabel = `${p.year}-${String(p.month).padStart(2, '0')}`;
              return (
                <button
                  key={p.billing_period_id}
                  type="button"
                  onClick={() => setSelectedPeriodId(p.billing_period_id)}
                  className={cn(
                    'flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all',
                    isSelected
                      ? 'border-primary-default bg-primary-subtle text-primary-contrast font-bold ring-1 ring-primary-focus'
                      : 'border-border-default bg-surface-default text-text-secondary hover:bg-surface-subtle'
                  )}
                >
                  <span>{periodLabel}</span>
                  <StatusBadge
                    status={p.status}
                    className="text-[10px] py-0 px-1.5"
                  />
                </button>
              );
            })
          )}
        </div>

        {/* Unlocked Period Notice */}
        {activePeriod && isPeriodUnlocked && (
          <div className="p-3 bg-amber-50 border border-amber-200 text-amber-900 rounded-lg text-xs flex items-center gap-2">
            <Icons.Info className="w-4 h-4 text-amber-600 flex-shrink-0" />
            <span>
              <strong>Draft figures:</strong> Not visible to students until locked by the Super Admin.
            </span>
          </div>
        )}
      </div>

      {/* Summary Stat Tiles */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="bg-surface-default p-4">
          <span className="text-xs text-text-secondary font-medium">Billed Students</span>
          <p className="text-2xl font-bold text-text-primary mt-1">{totals.studentsCount}</p>
        </Card>
        <Card className="bg-surface-default p-4">
          <span className="text-xs text-text-secondary font-medium">Total Billed</span>
          <p className="text-2xl font-bold text-primary-default mt-1">
            <MoneyText amountInRupees={totals.totalBilled} />
          </p>
        </Card>
        <Card className="bg-surface-default p-4">
          <span className="text-xs text-text-secondary font-medium">Extras Total</span>
          <p className="text-2xl font-bold text-text-primary mt-1">
            <MoneyText amountInRupees={totals.extrasTotal} />
          </p>
        </Card>
        <Card className="bg-surface-default p-4">
          <span className="text-xs text-text-secondary font-medium">Fees & Fines Total</span>
          <p className="text-2xl font-bold text-text-primary mt-1">
            <MoneyText amountInRupees={totals.feesFinesTotal} />
          </p>
        </Card>
      </div>

      {/* Search Bar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Icons.Search className="w-4 h-4 text-text-muted absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            type="text"
            placeholder="Search by student name, roll number, mess..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-2 text-xs border border-border-default rounded-lg bg-surface-default text-text-primary focus:outline-none focus:ring-1 focus:ring-primary-focus"
          />
        </div>
        {searchQuery && (
          <Button variant="ghost" size="sm" onClick={() => setSearchQuery('')} className="text-xs">
            Clear
          </Button>
        )}
      </div>

      {/* Error State */}
      {billsError && (
        <ErrorState
          errorCode={billsError.code}
          message={billsError.message}
          traceId={billsError.traceId}
          onRetry={() => selectedPeriodId && fetchBills(selectedPeriodId)}
        />
      )}

      {/* Data Table */}
      {loadingBills ? (
        <div className="space-y-3">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      ) : filteredBills.length === 0 ? (
        <EmptyState
          title="No bills found"
          description={
            searchQuery
              ? 'No student bills matched your search query.'
              : 'No bills have been calculated or generated for this period yet.'
          }
        />
      ) : (
        <Card className="p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-border-default bg-surface-subtle text-text-secondary font-semibold">
                  <th className="py-3 px-3">Student</th>
                  <th className="py-3 px-3">Roll No</th>
                  <th className="py-3 px-3">Mess</th>
                  <th className="py-3 px-3 text-right">Min Diets</th>
                  <th className="py-3 px-3 text-right">Actual Diets</th>
                  <th className="py-3 px-3 text-right">Diet Rate</th>
                  <th className="py-3 px-3 text-right">Meal Cost</th>
                  <th className="py-3 px-3 text-right">Extras</th>
                  <th className="py-3 px-3 text-right">Fees/Fines</th>
                  <th className="py-3 px-3 text-right">Final Total</th>
                  <th className="py-3 px-3 text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-default">
                {filteredBills.map((b) => (
                  <tr
                    key={b.bill_id}
                    onClick={() => openBillDetail(b)}
                    className="hover:bg-surface-subtle cursor-pointer transition-colors"
                  >
                    <td className="py-3 px-3 font-semibold text-text-primary">{b.student_name}</td>
                    <td className="py-3 px-3 text-text-secondary font-mono">{b.student_roll_number}</td>
                    <td className="py-3 px-3 text-text-secondary">{b.mess_code}</td>
                    <td className="py-3 px-3 text-right text-text-secondary">{b.minimum_diet_count_snapshot}</td>
                    <td className="py-3 px-3 text-right text-text-secondary">{b.actual_meal_count}</td>
                    <td className="py-3 px-3 text-right text-text-secondary">
                      <MoneyText amountInRupees={Number(b.common_diet_rate_snapshot) || 0} />
                    </td>
                    <td className="py-3 px-3 text-right text-text-primary font-medium">
                      <MoneyText amountInRupees={Number(b.meal_component_amount) || 0} />
                    </td>
                    <td className="py-3 px-3 text-right text-text-secondary">
                      <MoneyText amountInRupees={Number(b.extra_charges_amount) || 0} />
                    </td>
                    <td className="py-3 px-3 text-right text-text-secondary">
                      <MoneyText amountInRupees={Number(b.adjustment_amount) || 0} />
                    </td>
                    <td className="py-3 px-3 text-right font-bold text-primary-default">
                      <MoneyText amountInRupees={Number(b.final_amount) || 0} />
                    </td>
                    <td className="py-3 px-3 text-center">
                      <StatusBadge
                        status={b.status}
                        className="text-[10px] py-0.5 px-2"
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Bill Detail Breakdown Drawer */}
      {selectedBill && (
        <Drawer
          isOpen={Boolean(selectedBill)}
          onClose={() => setSelectedBill(null)}
          title={`Bill Details: ${selectedBill.student_name}`}
        >
          <div className="space-y-6 text-sm">
            {/* Student & Period Meta */}
            <div className="bg-surface-subtle p-3 rounded-lg border border-border-default space-y-1.5 text-xs">
              <div className="flex justify-between">
                <span className="text-text-secondary">Roll Number:</span>
                <span className="font-mono font-bold text-text-primary">{selectedBill.student_roll_number}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Mess Assignment:</span>
                <span className="font-semibold text-text-primary">{selectedBill.mess_code}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Billing Period:</span>
                <span className="font-semibold text-text-primary">
                  {selectedBill.period_year}-{String(selectedBill.period_month).padStart(2, '0')} (
                  {selectedBill.period_status})
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Final Amount:</span>
                <span className="font-bold text-primary-default text-sm">
                  <MoneyText amountInRupees={Number(selectedBill.final_amount) || 0} />
                </span>
              </div>
            </div>

            {loadingDetail ? (
              <div className="space-y-2">
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
              </div>
            ) : (
              <>
                {/* 1. Diet Calculation Lines */}
                <div className="space-y-2">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-text-secondary">
                    Diet Calculation Breakdown
                  </h4>
                  <div className="border border-border-default rounded-lg overflow-hidden text-xs">
                    <table className="w-full text-left">
                      <thead className="bg-surface-subtle border-b border-border-default text-text-secondary font-medium">
                        <tr>
                          <th className="py-2 px-3">Type</th>
                          <th className="py-2 px-3">Description</th>
                          <th className="py-2 px-3 text-right">Qty</th>
                          <th className="py-2 px-3 text-right">Rate</th>
                          <th className="py-2 px-3 text-right">Amount</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border-default">
                        {/* Minimum Diet line highlighting larger of minimum vs actual */}
                        <tr className="bg-primary-subtle/30 font-medium">
                          <td className="py-2 px-3 text-primary-contrast font-bold">Diet Rule</td>
                          <td className="py-2 px-3 text-text-primary">
                            Policy Min: {selectedBill.minimum_diet_count_snapshot} vs Actual:{' '}
                            {selectedBill.actual_meal_count}
                            <span className="block text-[10px] text-text-muted">
                              (Larger count is billed per Minimum Diet Policy)
                            </span>
                          </td>
                          <td className="py-2 px-3 text-right font-bold">
                            {Math.max(selectedBill.minimum_diet_count_snapshot, selectedBill.actual_meal_count)}
                          </td>
                          <td className="py-2 px-3 text-right">
                            <MoneyText amountInRupees={Number(selectedBill.common_diet_rate_snapshot) || 0} />
                          </td>
                          <td className="py-2 px-3 text-right font-bold text-text-primary">
                            <MoneyText amountInRupees={Number(selectedBill.meal_component_amount) || 0} />
                          </td>
                        </tr>

                        {selectedBill.lines?.map((line) => (
                          <tr key={line.bill_line_id}>
                            <td className="py-2 px-3 font-semibold text-text-secondary">{line.line_type}</td>
                            <td className="py-2 px-3 text-text-primary">{line.description}</td>
                            <td className="py-2 px-3 text-right text-text-secondary">{line.quantity}</td>
                            <td className="py-2 px-3 text-right text-text-secondary">
                              <MoneyText amountInRupees={Number(line.unit_rate) || 0} />
                            </td>
                            <td className="py-2 px-3 text-right font-semibold text-text-primary">
                              <MoneyText amountInRupees={Number(line.amount) || 0} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* 2. Extra Item Charges */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-text-secondary">
                      Extra Items Consumed
                    </h4>
                    <span className="text-xs font-bold text-text-primary">
                      Total: <MoneyText amountInRupees={Number(selectedBill.extra_charges_amount) || 0} />
                    </span>
                  </div>
                  {Number(selectedBill.extra_charges_amount) === 0 ? (
                    <p className="text-xs text-text-muted italic py-1">No extra item transactions in this period.</p>
                  ) : (
                    <p className="text-xs text-text-secondary">
                      Itemized extra transactions summarized under total extras of{' '}
                      <MoneyText amountInRupees={Number(selectedBill.extra_charges_amount) || 0} />.
                    </p>
                  )}
                </div>

                {/* 3. Fees and Fines (Adjustments) */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-text-secondary">
                      Fees & Fines Adjustments
                    </h4>
                    <span className="text-xs font-bold text-text-primary">
                      Total: <MoneyText amountInRupees={Number(selectedBill.adjustment_amount) || 0} />
                    </span>
                  </div>

                  {!selectedBill.adjustments || selectedBill.adjustments.length === 0 ? (
                    <p className="text-xs text-text-muted italic py-1">No fees or fines applied to this bill.</p>
                  ) : (
                    <div className="space-y-2">
                      {selectedBill.adjustments.map((adj) => (
                        <div
                          key={adj.adjustment_id}
                          className="p-2.5 rounded border border-border-default bg-surface-subtle text-xs space-y-1"
                        >
                          <div className="flex justify-between items-center font-semibold">
                            <span
                              className={
                                adj.adjustment_type === 'FINE' ? 'text-danger-default' : 'text-primary-default'
                              }
                            >
                              {adj.adjustment_type}: <MoneyText amountInRupees={Number(adj.amount) || 0} />
                            </span>
                            <span className="text-[10px] text-text-muted">
                              {adj.created_at ? new Date(adj.created_at).toLocaleDateString() : ''}
                            </span>
                          </div>
                          <p className="text-text-primary">{adj.reason}</p>
                          {adj.created_by_name && (
                            <span className="text-[10px] text-text-muted block">Applied by: {adj.created_by_name}</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </>
            )}

            <div className="pt-4 border-t border-border-default">
              <Button variant="secondary" className="w-full text-xs" onClick={() => setSelectedBill(null)}>
                Close
              </Button>
            </div>
          </div>
        </Drawer>
      )}
    </div>
  );
};

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Card } from '../../components/Card';
import { Button } from '../../components/Button';
import { StatusBadge } from '../../components/StatusBadge';
import { Skeleton } from '../../components/Skeleton';
import { EmptyState } from '../../components/EmptyState';
import { ErrorState } from '../../components/ErrorState';
import { Drawer } from '../../components/Drawer';
import { ReasonDialog } from '../../components/ReasonDialog';
import { Icons } from '../../components/Icons';
import { apiClient } from '../../api/client';
import { useAuth } from '../../state/auth';

export interface MealConsumption {
  meal_consumption_id: number;
  transaction_id: string;
  student_id: number;
  roll_number_snapshot: string;
  student_name: string;
  mess_id: number;
  mess_name: string;
  meal_type_id: number;
  meal_type_code: string;
  meal_date: string;
  price_at_transaction: string | number;
  transaction_timestamp: string;
  verification_method: string;
  verification_result: string;
  source: string;
  accepted_at: string;
  is_removed?: boolean;
}

export interface AttendanceCorrection {
  correction_id: number;
  correction_transaction_id: string;
  student_id: number;
  student_name?: string;
  roll_number?: string;
  mess_id?: number;
  meal_date: string;
  meal_type_code: string;
  action: 'ADD_MISSING' | 'REMOVE_INCORRECT';
  original_meal_consumption_id?: number | null;
  requested_at: string;
  applied_at: string;
  reason: string;
  actor_email?: string;
  status: string;
}

const DEFAULT_DAYS_BACK = 7;

export const AttendancePage: React.FC = () => {
  const { assignment } = useAuth();
  const hostelId = assignment?.hostel_id;

  // Date Range (default: last 7 days)
  const [startDate, setStartDate] = useState<string>(() => {
    const d = new Date();
    d.setDate(d.getDate() - DEFAULT_DAYS_BACK);
    return d.toISOString().split('T')[0];
  });
  const [endDate, setEndDate] = useState<string>(() => {
    return new Date().toISOString().split('T')[0];
  });

  // Filters
  const [mealTypeFilter, setMealTypeFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Data
  const [records, setRecords] = useState<MealConsumption[]>([]);
  const [corrections, setCorrections] = useState<AttendanceCorrection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ code: string; message: string; traceId?: string } | null>(null);

  // Selected row for Drawer
  const [selectedRecord, setSelectedRecord] = useState<MealConsumption | null>(null);

  // Dialogs
  const [correctDialogOpen, setCorrectDialogOpen] = useState(false);
  const [recordToCorrect, setRecordToCorrect] = useState<MealConsumption | null>(null);
  const [correctSubmitting, setCorrectSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // Add Missing Meal Modal
  const [addMissingModalOpen, setAddMissingModalOpen] = useState(false);
  const [addStudentId, setAddStudentId] = useState<string>('');
  const [addRollNumber, setAddRollNumber] = useState<string>('');
  const [addMealDate, setAddMealDate] = useState<string>(() => new Date().toISOString().split('T')[0]);
  const [addMealType, setAddMealType] = useState<string>('BREAKFAST');
  const [addReason, setAddReason] = useState<string>('');
  const [addingMissing, setAddingMissing] = useState(false);
  const [addMissingError, setAddMissingError] = useState<string | null>(null);

  // Online check
  const isOnline = typeof navigator !== 'undefined' ? navigator.onLine : true;

  // Fetch Attendance & Corrections
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (startDate) params.set('start_date', startDate);
      if (endDate) params.set('end_date', endDate);
      if (mealTypeFilter !== 'ALL') params.set('meal_type', mealTypeFilter);

      const [attRes, corrRes] = await Promise.all([
        apiClient.get<any>(`/api/v1/attendance?${params.toString()}`),
        apiClient.get<any>(`/api/v1/attendance/corrections?start_date=${startDate}&end_date=${endDate}`),
      ]);

      const attList = attRes.results || attRes;
      const corrList = corrRes.results || corrRes;

      const rawCorrections: AttendanceCorrection[] = Array.isArray(corrList) ? corrList : [];
      setCorrections(rawCorrections);

      // Map removed status onto consumptions if a correction marked them REMOVE_INCORRECT
      const removedIds = new Set(
        rawCorrections
          .filter((c) => c.action === 'REMOVE_INCORRECT' && c.original_meal_consumption_id)
          .map((c) => c.original_meal_consumption_id)
      );

      const mappedRecords: MealConsumption[] = (Array.isArray(attList) ? attList : []).map((r) => ({
        ...r,
        is_removed: removedIds.has(r.meal_consumption_id),
      }));

      setRecords(mappedRecords);
    } catch (err: any) {
      setError({
        code: err.code || 'LOAD_FAILED',
        message: err.message || 'Failed to load attendance records',
        traceId: err.trace_id,
      });
    } finally {
      setLoading(false);
    }
  }, [startDate, endDate, mealTypeFilter]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Handle Correct Attendance (REMOVE_INCORRECT)
  const handleConfirmCorrect = async (reasonText: string) => {
    if (!recordToCorrect) return;
    if (!isOnline) {
      setActionError('Corrections require an active internet connection (online only).');
      return;
    }

    setCorrectSubmitting(true);
    setActionError(null);
    try {
      const transactionId = crypto.randomUUID();
      await apiClient.post('/api/v1/attendance/corrections', {
        correction_transaction_id: transactionId,
        student_id: recordToCorrect.student_id,
        meal_date: recordToCorrect.meal_date,
        meal_type: recordToCorrect.meal_type_code,
        action: 'REMOVE_INCORRECT',
        reason: reasonText,
      });

      setCorrectDialogOpen(false);
      setRecordToCorrect(null);
      await fetchData();
    } catch (err: any) {
      setActionError(
        err.message || 'Failed to correct attendance. The billing period may be locked or correction window closed.'
      );
    } finally {
      setCorrectSubmitting(false);
    }
  };

  // Handle Add Missing Meal
  const handleAddMissingMeal = async () => {
    if (!isOnline) {
      setAddMissingError('Corrections require an active internet connection (online only).');
      return;
    }
    if (!addStudentId.trim() && !addRollNumber.trim()) {
      setAddMissingError('Student ID or Roll Number is required.');
      return;
    }
    if (addReason.trim().length < 5) {
      setAddMissingError('Reason must be at least 5 characters long.');
      return;
    }

    setAddingMissing(true);
    setAddMissingError(null);
    try {
      const transactionId = crypto.randomUUID();
      const studentIdNum = parseInt(addStudentId) || 1;

      await apiClient.post('/api/v1/attendance/corrections', {
        correction_transaction_id: transactionId,
        student_id: studentIdNum,
        meal_date: addMealDate,
        meal_type: addMealType,
        action: 'ADD_MISSING',
        reason: addReason.trim(),
      });

      setAddMissingModalOpen(false);
      setAddStudentId('');
      setAddRollNumber('');
      setAddReason('');
      await fetchData();
    } catch (err: any) {
      setAddMissingError(
        err.message || 'Failed to add meal. The billing period may be locked or student is out of scope.'
      );
    } finally {
      setAddingMissing(false);
    }
  };

  // Filter records
  const filteredRecords = useMemo(() => {
    if (!searchQuery.trim()) return records;
    const q = searchQuery.toLowerCase();
    return records.filter(
      (r) =>
        r.student_name?.toLowerCase().includes(q) ||
        r.roll_number_snapshot?.toLowerCase().includes(q) ||
        r.mess_name?.toLowerCase().includes(q)
    );
  }, [records, searchQuery]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-text-primary">Attendance & Corrections</h1>
          <p className="text-sm text-text-secondary mt-1">
            Review meal consumption logs and submit audited attendance corrections for{' '}
            <span className="font-semibold text-text-primary">
              {assignment?.hostel_name || (hostelId ? `Hostel ${hostelId}` : 'your hostel')}
            </span>
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="primary"
            icon={<Icons.Plus className="w-4 h-4" />}
            onClick={() => {
              setAddMissingError(null);
              setAddMissingModalOpen(true);
            }}
          >
            Add Missing Meal
          </Button>
        </div>
      </div>

      {/* Online Status notice if offline */}
      {actionError && (
        <div className="p-3 bg-danger-subtle text-danger-contrast rounded-lg border border-danger-default text-xs flex items-center justify-between">
          <span>{actionError}</span>
          <button type="button" onClick={() => setActionError(null)} className="font-bold ml-2">
            ×
          </button>
        </div>
      )}

      {!isOnline && (
        <div className="p-3 bg-danger-subtle text-danger-contrast rounded-lg border border-danger-default text-xs flex items-center gap-2">
          <Icons.Info className="w-4 h-4 flex-shrink-0" />
          <span>
            <strong>Offline Mode Detected:</strong> Attendance corrections can only be submitted while online.
          </span>
        </div>
      )}

      {/* Filter Bar */}
      <Card className="bg-surface-default p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div>
            <label className="block text-xs font-semibold text-text-secondary mb-1">From Date</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full px-3 py-1.5 text-xs border border-border-default rounded bg-surface-default text-text-primary focus:outline-none focus:ring-1 focus:ring-primary-focus"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-secondary mb-1">To Date</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full px-3 py-1.5 text-xs border border-border-default rounded bg-surface-default text-text-primary focus:outline-none focus:ring-1 focus:ring-primary-focus"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-secondary mb-1">Meal Type</label>
            <select
              value={mealTypeFilter}
              onChange={(e) => setMealTypeFilter(e.target.value)}
              className="w-full px-3 py-1.5 text-xs border border-border-default rounded bg-surface-default text-text-primary focus:outline-none focus:ring-1 focus:ring-primary-focus"
            >
              <option value="ALL">All Meals</option>
              <option value="BREAKFAST">Breakfast</option>
              <option value="LUNCH">Lunch</option>
              <option value="DINNER">Dinner</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-secondary mb-1">Search Student / Mess</label>
            <input
              type="text"
              placeholder="Roll number or student name..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full px-3 py-1.5 text-xs border border-border-default rounded bg-surface-default text-text-primary focus:outline-none focus:ring-1 focus:ring-primary-focus"
            />
          </div>
        </div>
      </Card>

      {/* Error State */}
      {error && (
        <ErrorState
          errorCode={error.code}
          message={error.message}
          traceId={error.traceId}
          onRetry={fetchData}
        />
      )}

      {/* Data Table */}
      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      ) : filteredRecords.length === 0 ? (
        <EmptyState
          title="No attendance records found"
          description="No meal consumption events recorded for the selected date range and filter criteria."
        />
      ) : (
        <Card className="p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-border-default bg-surface-subtle text-text-secondary font-semibold">
                  <th className="py-3 px-3">Date</th>
                  <th className="py-3 px-3">Meal</th>
                  <th className="py-3 px-3">Roll No</th>
                  <th className="py-3 px-3">Student Name</th>
                  <th className="py-3 px-3">Mess</th>
                  <th className="py-3 px-3">Source</th>
                  <th className="py-3 px-3">State</th>
                  <th className="py-3 px-3">Recorded At</th>
                  <th className="py-3 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y border-border-default">
                {filteredRecords.map((r) => (
                  <tr
                    key={r.meal_consumption_id}
                    onClick={() => setSelectedRecord(r)}
                    className="hover:bg-surface-subtle cursor-pointer transition-colors"
                  >
                    <td className="py-3 px-3 font-semibold text-text-primary">{r.meal_date}</td>
                    <td className="py-3 px-3">
                      <span className="font-semibold text-text-primary">{r.meal_type_code}</span>
                    </td>
                    <td className="py-3 px-3 font-mono text-text-secondary">{r.roll_number_snapshot}</td>
                    <td className="py-3 px-3 font-medium text-text-primary">{r.student_name}</td>
                    <td className="py-3 px-3 text-text-secondary">{r.mess_name}</td>
                    <td className="py-3 px-3">
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-surface-subtle border border-border-default uppercase">
                        {r.source || r.verification_method || 'QR'}
                      </span>
                    </td>
                    <td className="py-3 px-3">
                      <StatusBadge
                        status={r.is_removed ? 'INACTIVE' : 'ACTIVE'}
                        className="text-[10px] py-0 px-1.5"
                      />
                    </td>
                    <td className="py-3 px-3 text-text-secondary">
                      {r.transaction_timestamp ? new Date(r.transaction_timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}
                    </td>
                    <td className="py-3 px-3 text-right">
                      {!r.is_removed && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-[11px] text-danger-default hover:text-danger-contrast"
                          onClick={(e) => {
                            e.stopPropagation();
                            setActionError(null);
                            setRecordToCorrect(r);
                            setCorrectDialogOpen(true);
                          }}
                        >
                          Correct
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Row Detail Drawer */}
      {selectedRecord && (
        <Drawer
          isOpen={Boolean(selectedRecord)}
          onClose={() => setSelectedRecord(null)}
          title={`Attendance Record #${selectedRecord.meal_consumption_id}`}
        >
          <div className="space-y-6 text-sm">
            <div className="bg-surface-subtle p-3 rounded-lg border border-border-default space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-text-secondary">Student:</span>
                <span className="font-bold text-text-primary">{selectedRecord.student_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Roll Number:</span>
                <span className="font-mono text-text-primary">{selectedRecord.roll_number_snapshot}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Meal Date:</span>
                <span className="font-medium text-text-primary">{selectedRecord.meal_date}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Meal Type:</span>
                <span className="font-medium text-text-primary">{selectedRecord.meal_type_code}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Mess:</span>
                <span className="font-medium text-text-primary">{selectedRecord.mess_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Status:</span>
                <StatusBadge
                  status={selectedRecord.is_removed ? 'INACTIVE' : 'ACTIVE'}
                />
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Transaction ID:</span>
                <span className="font-mono text-[10px] text-text-muted">{selectedRecord.transaction_id}</span>
              </div>
            </div>

            {/* Corrections History for this student / meal */}
            <div className="space-y-3">
              <h4 className="text-xs font-bold uppercase tracking-wider text-text-secondary">
                Audited Corrections History
              </h4>
              {corrections.filter(
                (c) =>
                  c.student_id === selectedRecord.student_id &&
                  c.meal_date === selectedRecord.meal_date
              ).length === 0 ? (
                <p className="text-xs text-text-muted italic">No corrections recorded for this date.</p>
              ) : (
                <div className="space-y-2">
                  {corrections
                    .filter(
                      (c) =>
                        c.student_id === selectedRecord.student_id &&
                        c.meal_date === selectedRecord.meal_date
                    )
                    .map((corr) => (
                      <div
                        key={corr.correction_id}
                        className="p-2.5 rounded border border-border-default bg-surface-subtle text-xs space-y-1"
                      >
                        <div className="flex justify-between items-center font-semibold">
                          <span
                            className={
                              corr.action === 'REMOVE_INCORRECT' ? 'text-danger-default' : 'text-primary-default'
                            }
                          >
                            {corr.action} ({corr.meal_type_code})
                          </span>
                          <span className="text-[10px] text-text-muted">
                            {corr.applied_at ? new Date(corr.applied_at).toLocaleDateString() : ''}
                          </span>
                        </div>
                        <p className="text-text-primary font-medium">"{corr.reason}"</p>
                        {corr.actor_email && (
                          <span className="text-[10px] text-text-muted block">By: {corr.actor_email}</span>
                        )}
                      </div>
                    ))}
                </div>
              )}
            </div>

            <div className="pt-4 border-t border-border-default flex flex-col gap-2">
              {!selectedRecord.is_removed && (
                <Button
                  variant="danger"
                  className="w-full text-xs"
                  onClick={() => {
                    setActionError(null);
                    setRecordToCorrect(selectedRecord);
                    setCorrectDialogOpen(true);
                  }}
                >
                  Mark Incorrect / Remove Attendance
                </Button>
              )}
              <Button variant="secondary" className="w-full text-xs" onClick={() => setSelectedRecord(null)}>
                Close
              </Button>
            </div>
          </div>
        </Drawer>
      )}

      {/* Correct Attendance Reason Dialog */}
      {correctDialogOpen && recordToCorrect && (
        <ReasonDialog
          isOpen={correctDialogOpen}
          title="Correct Attendance Record"
          description={`Please provide a mandatory reason for removing the meal attendance record for ${recordToCorrect.student_name} (${recordToCorrect.meal_date} - ${recordToCorrect.meal_type_code}). Minimum 5 characters.`}
          confirmLabel="Confirm Correction"
          minLength={5}
          loading={correctSubmitting}
          onConfirm={handleConfirmCorrect}
          onClose={() => {
            setCorrectDialogOpen(false);
            setRecordToCorrect(null);
          }}
        />
      )}

      {/* Add Missing Meal Modal */}
      {addMissingModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <Card className="max-w-md w-full bg-surface-default shadow-xl p-6">
            <div className="flex items-center justify-between border-b border-border-default pb-3">
              <h2 className="text-base font-bold text-text-primary">Add Missing Meal</h2>
              <button
                type="button"
                onClick={() => setAddMissingModalOpen(false)}
                className="text-text-muted hover:text-text-primary"
              >
                <Icons.X className="w-5 h-5" />
              </button>
            </div>

            {addMissingError && (
              <div className="mt-3 p-2.5 text-xs bg-danger-subtle text-danger-contrast rounded border border-danger-default">
                {addMissingError}
              </div>
            )}

            <div className="mt-4 space-y-3">
              <div>
                <label className="block text-xs font-semibold text-text-secondary mb-1">
                  Student ID <span className="text-danger-default">*</span>
                </label>
                <input
                  type="number"
                  placeholder="e.g. 101"
                  value={addStudentId}
                  onChange={(e) => setAddStudentId(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-border-default rounded bg-surface-default text-text-primary focus:outline-none focus:ring-1 focus:ring-primary-focus"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-text-secondary mb-1">
                  Meal Date <span className="text-danger-default">*</span>
                </label>
                <input
                  type="date"
                  value={addMealDate}
                  onChange={(e) => setAddMealDate(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-border-default rounded bg-surface-default text-text-primary focus:outline-none focus:ring-1 focus:ring-primary-focus"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-text-secondary mb-1">
                  Meal Type <span className="text-danger-default">*</span>
                </label>
                <select
                  value={addMealType}
                  onChange={(e) => setAddMealType(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-border-default rounded bg-surface-default text-text-primary focus:outline-none focus:ring-1 focus:ring-primary-focus"
                >
                  <option value="BREAKFAST">Breakfast</option>
                  <option value="LUNCH">Lunch</option>
                  <option value="DINNER">Dinner</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-text-secondary mb-1">
                  Reason <span className="text-danger-default">* (minimum 5 characters)</span>
                </label>
                <textarea
                  rows={2}
                  placeholder="Reason for manual addition (e.g. Scanner power failure at entrance)"
                  value={addReason}
                  onChange={(e) => setAddReason(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-border-default rounded bg-surface-default text-text-primary focus:outline-none focus:ring-1 focus:ring-primary-focus"
                />
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-2 border-t border-border-default pt-3">
              <Button variant="ghost" onClick={() => setAddMissingModalOpen(false)} disabled={addingMissing}>
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleAddMissingMeal}
                loading={addingMissing}
                disabled={!addStudentId || addReason.trim().length < 5}
              >
                Submit Correction
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
};

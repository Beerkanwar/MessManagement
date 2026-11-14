import React, { useState, useEffect, useCallback } from 'react';
import { Button } from '../../components/Button';
import { FilterBar } from '../../components/FilterBar';
import { Tabs } from '../../components/Tabs';
import { DataTable, Column } from '../../components/DataTable';
import { Drawer } from '../../components/Drawer';
import { StatusBadge } from '../../components/StatusBadge';
import { ReasonDialog } from '../../components/ReasonDialog';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { DateText } from '../../components/DateText';
import { Skeleton } from '../../components/Skeleton';
import { ErrorState } from '../../components/ErrorState';
import { Icons } from '../../components/Icons';
import { apiClient } from '../../api/client';
import { useAuth } from '../../state/auth';

interface VerificationRow {
  assignment_id: number;
  student_id: number;
  roll_number: string;
  name: string;
  email: string;
  mess_name: string;
  hostel_name: string;
  effective_from: string;
  status: 'PENDING_VERIFICATION' | 'ACTIVE' | 'REJECTED' | 'PENDING' | 'VERIFIED';
  created_at: string;
  import_batch_id?: number | string;
  history?: Array<{ event: string; at: string; by: string; notes?: string }>;
}

export const StudentVerificationPage: React.FC = () => {
  const { assignment } = useAuth();
  const [activeTab, setActiveTab] = useState<'PENDING' | 'VERIFIED' | 'REJECTED'>('PENDING');
  const [searchQuery, setSearchQuery] = useState('');
  const [messFilter, setMessFilter] = useState('');
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());

  // Data
  const [rows, setRows] = useState<VerificationRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ code: string; message: string; traceId?: string } | null>(null);

  // Detail Drawer
  const [selectedRow, setSelectedRow] = useState<VerificationRow | null>(null);

  // Single Action Dialogs
  const [rejectTargetId, setRejectTargetId] = useState<number | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  // Bulk Verify Confirm & Results
  const [showBulkConfirm, setShowBulkConfirm] = useState(false);
  const [bulkResults, setBulkResults] = useState<Array<{
    assignment_id: number;
    success: boolean;
    error?: string;
  }> | null>(null);

  const scopeLabel = assignment?.hostel_name || 'Assigned Hostel';

  const fetchVerifications = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.get<any>('/students/verifications');
      const list = data?.results || (Array.isArray(data) ? data : []);

      // Normalize row structure from backend serializer
      const formatted: VerificationRow[] = list.map((item: any) => ({
        assignment_id: item.assignment_id || item.id,
        student_id: item.student?.student_id || item.student_id,
        roll_number: item.student?.roll_number || item.roll_number || 'N/A',
        name: item.student?.full_name || item.student?.user?.full_name || item.name || 'Student',
        email: item.student?.email || item.student?.user?.email || item.email || '',
        mess_name: item.mess?.name || item.mess_name || 'Main Mess',
        hostel_name: item.hostel?.name || item.hostel_name || scopeLabel,
        effective_from: item.effective_from || item.created_at,
        status: item.status || 'PENDING_VERIFICATION',
        created_at: item.created_at || new Date().toISOString(),
        import_batch_id: item.import_batch_id,
        history: item.history || [
          { event: 'Created', at: item.created_at || new Date().toISOString(), by: 'Super Admin Import' },
        ],
      }));
      setRows(formatted);
    } catch (err: any) {
      setError({
        code: err.code || 'VERIFICATIONS_FETCH_FAILED',
        message: err.message || 'Unable to load verification roster.',
        traceId: err.traceId,
      });
    } finally {
      setLoading(false);
    }
  }, [scopeLabel]);

  useEffect(() => {
    fetchVerifications();
  }, [fetchVerifications]);

  // Tab Filtering
  const filteredRows = rows.filter((r) => {
    if (activeTab === 'PENDING' && r.status !== 'PENDING_VERIFICATION' && r.status !== 'PENDING') return false;
    if (activeTab === 'VERIFIED' && r.status !== 'ACTIVE' && r.status !== 'VERIFIED') return false;
    if (activeTab === 'REJECTED' && r.status !== 'REJECTED') return false;

    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      const matchRoll = r.roll_number.toLowerCase().includes(q);
      const matchName = r.name.toLowerCase().includes(q);
      const matchEmail = r.email.toLowerCase().includes(q);
      if (!matchRoll && !matchName && !matchEmail) return false;
    }

    if (messFilter && r.mess_name !== messFilter) return false;

    return true;
  });

  // Single Verify
  const handleVerifySingle = async (assignmentId: number) => {
    setActionLoading(true);
    try {
      await apiClient.post(`/students/verifications/${assignmentId}/verify`, { notes: 'Verified by clerk' });
      // Update local state
      setRows((prev) =>
        prev.map((r) => (r.assignment_id === assignmentId ? { ...r, status: 'ACTIVE' } : r))
      );
      if (selectedRow?.assignment_id === assignmentId) {
        setSelectedRow((prev) => (prev ? { ...prev, status: 'ACTIVE' } : null));
      }
    } catch (err: any) {
      alert(err.message || 'Verification failed');
    } finally {
      setActionLoading(false);
    }
  };

  // Single Reject with mandatory reason
  const handleRejectSingle = async (reason: string) => {
    if (!rejectTargetId) return;
    setActionLoading(true);
    try {
      await apiClient.post(`/students/verifications/${rejectTargetId}/reject`, { notes: reason });
      setRows((prev) =>
        prev.map((r) => (r.assignment_id === rejectTargetId ? { ...r, status: 'REJECTED' } : r))
      );
      if (selectedRow?.assignment_id === rejectTargetId) {
        setSelectedRow((prev) => (prev ? { ...prev, status: 'REJECTED' } : null));
      }
      setRejectTargetId(null);
    } catch (err: any) {
      alert(err.message || 'Rejection failed');
    } finally {
      setActionLoading(false);
    }
  };

  // Bulk Verify
  const handleBulkVerifyConfirm = async () => {
    setActionLoading(true);
    const ids = Array.from(selectedKeys).map((k) => Number(k));
    try {
      const res = await apiClient.post<{ results: Array<{ assignment_id: number; success: boolean; error?: string }> }>(
        '/students/verifications/bulk-verify',
        { assignment_ids: ids, notes: 'Bulk verified by hostel clerk' }
      );
      setBulkResults(res.results || []);
      setSelectedKeys(new Set());
      setShowBulkConfirm(false);
      // Refresh list
      fetchVerifications();
    } catch (err: any) {
      alert(err.message || 'Bulk verify operation failed');
    } finally {
      setActionLoading(false);
    }
  };

  const columns: Column<VerificationRow>[] = [
    {
      key: 'roll_number',
      header: 'Roll Number',
      sortable: true,
      render: (r) => <span className="font-mono font-bold text-text">{r.roll_number}</span>,
    },
    { key: 'name', header: 'Student Name', sortable: true },
    { key: 'email', header: 'College Email' },
    { key: 'mess_name', header: 'Mess' },
    {
      key: 'effective_from',
      header: 'Effective Date',
      render: (r) => <DateText date={r.effective_from} />,
    },
    {
      key: 'status',
      header: 'Status',
      render: (r) => <StatusBadge domain="assignment" status={r.status} />,
    },
    {
      key: 'created_at',
      header: 'Submitted',
      render: (r) => <DateText date={r.created_at} />,
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'right',
      render: (r) => (
        <div className="flex items-center justify-end gap-2" onClick={(e) => e.stopPropagation()}>
          {r.status === 'PENDING_VERIFICATION' && (
            <>
              <Button
                variant="primary"
                size="sm"
                onClick={() => handleVerifySingle(r.assignment_id)}
                disabled={actionLoading}
              >
                Verify
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={() => setRejectTargetId(r.assignment_id)}
                disabled={actionLoading}
              >
                Reject
              </Button>
            </>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setSelectedRow(r)}
          >
            Details
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6 select-none">
      {/* Header with read-only notice */}
      <div className="border-b border-border pb-5">
        <h2 className="text-[22px] font-bold text-text">Student Verification</h2>
        <p className="text-[13px] text-text-secondary mt-0.5">
          Review student registrations and approve dining attachments for <strong>{scopeLabel}</strong>.
        </p>

        <div className="mt-4 p-3 bg-info-subtle border border-[#BFDBFE] rounded-[8px] flex items-center gap-2.5 text-[13px] text-[#1E40AF]">
          <Icons.Info className="w-4 h-4 shrink-0 text-info" />
          <span>
            You can verify student details but not edit them; ask the Super Admin to correct roster mistakes.
          </span>
        </div>
      </div>

      {/* Tabs */}
      <Tabs
        activeKey={activeTab}
        onChange={(k) => {
          setActiveTab(k as any);
          setSelectedKeys(new Set());
        }}
        items={[
          {
            key: 'PENDING',
            label: 'Pending Verification',
            count: rows.filter((r) => r.status === 'PENDING_VERIFICATION').length,
          },
          {
            key: 'VERIFIED',
            label: 'Verified Students',
            count: rows.filter((r) => r.status === 'ACTIVE').length,
          },
          {
            key: 'REJECTED',
            label: 'Rejected',
            count: rows.filter((r) => r.status === 'REJECTED').length,
          },
        ]}
      />

      {/* Filter Bar & Bulk Actions */}
      <FilterBar
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        searchPlaceholder="Search by roll number, name or email..."
        filters={
          <select
            value={messFilter}
            onChange={(e) => setMessFilter(e.target.value)}
            className="h-[38px] px-3 text-[13px] bg-bg border border-border rounded-[6px] text-text"
          >
            <option value="">All Messes</option>
            <option value="Main Mess North">Main Mess North</option>
            <option value="Main Mess South">Main Mess South</option>
            <option value="PG Dining Hall">PG Dining Hall</option>
          </select>
        }
        actions={
          activeTab === 'PENDING' && selectedKeys.size > 0 ? (
            <Button
              variant="primary"
              size="sm"
              onClick={() => setShowBulkConfirm(true)}
              icon={<Icons.Check className="w-4 h-4" />}
            >
              Verify Selected ({selectedKeys.size})
            </Button>
          ) : null
        }
      />

      {/* Error state */}
      {error && (
        <ErrorState
          errorCode={error.code}
          message={error.message}
          traceId={error.traceId}
          onRetry={fetchVerifications}
        />
      )}

      {/* Loading */}
      {loading && !error && (
        <div className="space-y-3 p-6 bg-surface border border-border rounded-[10px]">
          <Skeleton height={32} width="30%" />
          <Skeleton height={24} />
          <Skeleton height={24} />
          <Skeleton height={24} />
        </div>
      )}

      {/* Data Table */}
      {!loading && !error && (
        <DataTable
          columns={columns}
          data={filteredRows}
          keyExtractor={(r) => String(r.assignment_id)}
          selectable={activeTab === 'PENDING'}
          selectedKeys={selectedKeys}
          onSelectionChange={setSelectedKeys}
          onRowClick={setSelectedRow}
          emptyTitle={`No ${activeTab.toLowerCase()} verifications found`}
          emptyDescription="There are no student assignments matching your current tab or filter."
        />
      )}

      {/* Row Detail Drawer (Read-only record and verification history) */}
      <Drawer
        isOpen={Boolean(selectedRow)}
        onClose={() => setSelectedRow(null)}
        title="Student Registration Record"
        subtitle="Read-only assignment record (Super Admin manages edits)"
        footer={
          selectedRow?.status === 'PENDING_VERIFICATION' ? (
            <div className="flex items-center justify-end gap-3 w-full">
              <Button
                variant="danger"
                size="sm"
                onClick={() => {
                  setRejectTargetId(selectedRow.assignment_id);
                }}
              >
                Reject Assignment
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  handleVerifySingle(selectedRow.assignment_id);
                }}
              >
                Verify Student
              </Button>
            </div>
          ) : (
            <Button variant="secondary" size="sm" onClick={() => setSelectedRow(null)}>
              Close
            </Button>
          )
        }
      >
        {selectedRow && (
          <div className="space-y-6 text-[13px]">
            <div className="p-4 bg-bg rounded-[8px] border border-border space-y-2">
              <div className="flex justify-between">
                <span className="text-text-muted">Roll Number:</span>
                <span className="font-mono font-bold text-text">{selectedRow.roll_number}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">Full Name:</span>
                <span className="font-semibold text-text">{selectedRow.name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">College Email:</span>
                <span className="text-text">{selectedRow.email}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">Assigned Hostel:</span>
                <span className="text-text">{selectedRow.hostel_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">Assigned Mess:</span>
                <span className="text-text">{selectedRow.mess_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">Status:</span>
                <StatusBadge domain="assignment" status={selectedRow.status} />
              </div>
            </div>

            <div>
              <h4 className="font-semibold text-text mb-3">Audit History</h4>
              <div className="border border-border rounded-[8px] divide-y divide-border bg-surface">
                {selectedRow.history?.map((h, i) => (
                  <div key={i} className="p-3 text-[12px] space-y-1">
                    <div className="flex justify-between font-medium">
                      <span>{h.event}</span>
                      <DateText date={h.at} includeTime />
                    </div>
                    <span className="text-text-muted block">By: {h.by}</span>
                    {h.notes && <p className="text-text italic">Notes: "{h.notes}"</p>}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </Drawer>

      {/* Reject Reason Dialog (Mandatory notes) */}
      <ReasonDialog
        isOpen={Boolean(rejectTargetId)}
        onClose={() => setRejectTargetId(null)}
        onConfirm={handleRejectSingle}
        title="Reject Student Assignment"
        description="State why this student is not admitted to your hostel. Rejection notes are mandatory and reviewed by Super Admin."
        placeholder="Enter mandatory rejection reason (e.g., student room cancelled, wrong hostel)..."
        confirmLabel="Confirm Rejection"
        variant="danger"
        minLength={5}
        loading={actionLoading}
      />

      {/* Bulk Verify Confirm Dialog */}
      <ConfirmDialog
        isOpen={showBulkConfirm}
        onClose={() => setShowBulkConfirm(false)}
        onConfirm={handleBulkVerifyConfirm}
        title={`Verify ${selectedKeys.size} Students?`}
        description={`Are you sure you want to approve dining attachments for all ${selectedKeys.size} selected students?`}
        confirmLabel="Verify All Selected"
        loading={actionLoading}
      />

      {/* Bulk Result Dialog */}
      {bulkResults && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="fixed inset-0 bg-[#0F172A]/40 backdrop-blur-[1px]" onClick={() => setBulkResults(null)} />
          <div className="relative w-full max-w-lg bg-surface border border-border rounded-[16px] shadow-2xl p-6 z-10 space-y-4">
            <h3 className="text-[17px] font-bold text-text">Bulk Verification Results</h3>
            <div className="max-h-60 overflow-y-auto border border-border rounded-[8px] divide-y divide-border text-[13px]">
              {bulkResults.map((res) => (
                <div key={res.assignment_id} className="p-3 flex items-center justify-between">
                  <span>Assignment #{res.assignment_id}</span>
                  {res.success ? (
                    <span className="text-success font-semibold flex items-center gap-1">
                      <Icons.Check className="w-4 h-4" /> Done
                    </span>
                  ) : (
                    <span className="text-danger font-semibold flex items-center gap-1">
                      <Icons.X className="w-4 h-4" /> Failed: {res.error}
                    </span>
                  )}
                </div>
              ))}
            </div>
            <div className="flex justify-end pt-2">
              <Button variant="primary" onClick={() => setBulkResults(null)}>
                Dismiss
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
export default StudentVerificationPage;

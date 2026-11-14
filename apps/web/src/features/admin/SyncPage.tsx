import React, { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../../api/client';
import { Card } from '../../components/Card';
import { DataTable, Column } from '../../components/DataTable';
import { Button } from '../../components/Button';
import { Drawer } from '../../components/Drawer';
import { TextField } from '../../components/TextField';
import { Select } from '../../components/Select';
import { Tabs } from '../../components/Tabs';
import { Banner } from '../../components/Banner';
import { Icons } from '../../components/Icons';

interface SyncConflict {
  conflict_id: number;
  conflict_type: string;
  detected_at: string;
  resolved_at?: string;
  resolution?: string;
  resolution_notes?: string;
  transaction?: {
    transaction_id: string;
    student_roll?: string;
    student_name?: string;
    mess_code?: string;
    item_code?: string;
    device_id?: string;
    manager_name?: string;
    recorded_at?: string;
    payload?: any;
  };
  server_facts?: {
    assignment_status?: string;
    is_paused?: boolean;
    period_status?: 'OPEN' | 'BILL_GENERATED' | 'REVIEWED' | 'LOCKED';
    period_year_month?: string;
  };
}

interface SyncBatch {
  sync_batch_id: number;
  device_id: string;
  manager_name?: string;
  mess_code?: string;
  transaction_count: number;
  success_count: number;
  conflict_count: number;
  duplicate_count: number;
  uploaded_at: string;
}

export const SyncPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'conflicts' | 'batches' | 'lookup'>('conflicts');
  const [conflictStatusFilter, setConflictStatusFilter] = useState<'OPEN' | 'RESOLVED'>('OPEN');
  const [conflicts, setConflicts] = useState<SyncConflict[]>([]);
  const [batches, setBatches] = useState<SyncBatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Conflict Drawer & Resolution (DEC-17)
  const [selectedConflict, setSelectedConflict] = useState<SyncConflict | null>(null);
  const [resolveNotes, setResolveNotes] = useState('');
  const [resolving, setResolving] = useState(false);
  const [resolveError, setResolveError] = useState<string | null>(null);

  // Transaction Lookup Tab
  const [lookupId, setLookupId] = useState('');
  const [lookupResult, setLookupResult] = useState<any | null>(null);
  const [lookupLoading, setLookupLoading] = useState(false);

  const fetchConflicts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.get<any>(`/sync/conflicts?status=${conflictStatusFilter}`);
      const list = Array.isArray(res) ? res : res?.results || [];
      setConflicts(list);
    } catch (err: any) {
      setError(err?.message || 'Failed to load sync conflicts.');
    } finally {
      setLoading(false);
    }
  }, [conflictStatusFilter]);

  const fetchBatches = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.get<any>('/sync/batches');
      const list = Array.isArray(res) ? res : res?.results || [];
      setBatches(list);
    } catch (err: any) {
      setError(err?.message || 'Failed to load upload batches.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'conflicts') {
      fetchConflicts();
    } else if (activeTab === 'batches') {
      fetchBatches();
    }
  }, [activeTab, fetchConflicts, fetchBatches]);

  const handleOpenConflictDrawer = async (conflict: SyncConflict) => {
    setSelectedConflict(conflict);
    setResolveNotes('');
    setResolveError(null);
    try {
      // Fetch full conflict detail if available
      const detail = await apiClient.get<SyncConflict>(`/sync/conflicts/${conflict.conflict_id}`);
      setSelectedConflict(detail);
    } catch {
      // Fallback to table item
    }
  };

  const handleResolveConflict = async (resolution: 'ACCEPT' | 'REJECT') => {
    if (!selectedConflict) return;
    setResolveError(null);

    if (!resolveNotes.trim()) {
      setResolveError('Resolution notes are mandatory (DEC-17).');
      return;
    }

    setResolving(true);
    try {
      await apiClient.post(`/sync/conflicts/${selectedConflict.conflict_id}/resolve`, {
        resolution: resolution === 'ACCEPT' ? 'ACCEPTED' : 'REJECTED',
        notes: resolveNotes.trim(),
      });
      setSuccessMsg(`Conflict #${selectedConflict.conflict_id} resolved as ${resolution}.`);
      setSelectedConflict(null);
      fetchConflicts();
    } catch (err: any) {
      setResolveError(err?.message || 'Failed to resolve sync conflict.');
    } finally {
      setResolving(false);
    }
  };

  const handleTransactionLookup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!lookupId.trim()) return;
    setLookupLoading(true);
    setLookupResult(null);
    try {
      const res = await apiClient.get<any>(`/sync/transactions?search=${encodeURIComponent(lookupId.trim())}`);
      const list = Array.isArray(res) ? res : res?.results || [];
      setLookupResult(list[0] || null);
      if (!list[0]) {
        setError(`No sync transaction found matching ID "${lookupId}".`);
      }
    } catch (err: any) {
      setError(err?.message || 'Transaction lookup failed.');
    } finally {
      setLookupLoading(false);
    }
  };

  const conflictColumns: Column<SyncConflict>[] = [
    {
      key: 'conflict_type',
      header: 'Conflict Type',
      render: (row) => <span className="font-semibold text-danger">{row.conflict_type}</span>,
    },
    {
      key: 'student',
      header: 'Student',
      render: (row) => (
        <div>
          <span className="font-mono font-bold text-text">
            {row.transaction?.student_roll || '—'}
          </span>
          <div className="text-[12px] text-text-muted">{row.transaction?.student_name}</div>
        </div>
      ),
    },
    {
      key: 'mess',
      header: 'Mess / Item',
      render: (row) => (
        <span>
          {row.transaction?.mess_code || '—'}
          {row.transaction?.item_code ? ` • ${row.transaction.item_code}` : ''}
        </span>
      ),
    },
    {
      key: 'detected_at',
      header: 'Detected',
      render: (row) => (
        <span className="text-[12px] text-text-secondary">
          {new Date(row.detected_at).toLocaleString()}
        </span>
      ),
    },
    {
      key: 'manager',
      header: 'Manager / Device',
      render: (row) => (
        <span className="text-[12px] text-text-secondary">
          {row.transaction?.manager_name || row.transaction?.device_id || 'Manager App'}
        </span>
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'right',
      render: (row) => (
        <Button
          size="sm"
          variant="secondary"
          onClick={() => handleOpenConflictDrawer(row)}
          icon={<Icons.FileText className="w-3.5 h-3.5" />}
        >
          {row.resolved_at ? 'View Details' : 'Review & Resolve'}
        </Button>
      ),
    },
  ];

  const batchColumns: Column<SyncBatch>[] = [
    {
      key: 'batch_id',
      header: 'Batch ID',
      render: (row) => <span className="font-mono font-bold text-text">#{row.sync_batch_id}</span>,
    },
    {
      key: 'mess_code',
      header: 'Mess & Device',
      render: (row) => (
        <div>
          <span className="font-semibold text-text">{row.mess_code || 'Mess Facility'}</span>
          <div className="text-[12px] text-text-muted">{row.device_id}</div>
        </div>
      ),
    },
    {
      key: 'counts',
      header: 'Transaction Outcomes',
      render: (row) => (
        <div className="flex items-center gap-2 text-[12px]">
          <span className="text-success font-medium">{row.success_count} Success</span>
          <span>•</span>
          <span className={row.conflict_count > 0 ? 'text-danger font-bold' : 'text-text-muted'}>
            {row.conflict_count} Conflicts
          </span>
          <span>•</span>
          <span className="text-text-muted">{row.duplicate_count} Dupes</span>
        </div>
      ),
    },
    {
      key: 'uploaded_at',
      header: 'Uploaded Time',
      render: (row) => (
        <span className="text-[12px] text-text-secondary">
          {new Date(row.uploaded_at).toLocaleString()}
        </span>
      ),
    },
  ];

  const isPeriodLocked = selectedConflict?.server_facts?.period_status === 'LOCKED';

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-5">
        <div>
          <h1 className="text-[22px] font-bold text-text">Synchronization & Conflicts</h1>
          <p className="text-[13px] text-text-secondary mt-0.5">
            Manager offline batch uploads, conflict adjudication (DEC-17), and transaction auditing
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
          { key: 'conflicts', label: 'Sync Conflicts' },
          { key: 'batches', label: 'Recent Upload Batches' },
          { key: 'lookup', label: 'Transaction Lookup' },
        ]}
      />

      {/* TAB 1: Conflicts */}
      {activeTab === 'conflicts' && (
        <div className="space-y-4">
          <div className="flex items-center gap-4">
            <Select
              label="Filter Conflict Status"
              value={conflictStatusFilter}
              onChange={(e) => setConflictStatusFilter(e.target.value as 'OPEN' | 'RESOLVED')}
              options={[
                { value: 'OPEN', label: 'Open Conflicts (Pending Review)' },
                { value: 'RESOLVED', label: 'Resolved Conflicts' },
              ]}
            />
          </div>

          <Card>
            <DataTable
              columns={conflictColumns}
              data={conflicts}
              loading={loading}
              keyExtractor={(c) => c.conflict_id.toString()}
              emptyMessage="No sync conflicts found matching status."
              onRowClick={(row) => handleOpenConflictDrawer(row)}
            />
          </Card>
        </div>
      )}

      {/* TAB 2: Upload Batches */}
      {activeTab === 'batches' && (
        <Card title="Recent Manager Sync Uploads">
          <DataTable
            columns={batchColumns}
            data={batches}
            loading={loading}
            keyExtractor={(b) => b.sync_batch_id.toString()}
            emptyMessage="No sync batches recorded yet."
          />
        </Card>
      )}

      {/* TAB 3: Transaction Lookup */}
      {activeTab === 'lookup' && (
        <div className="space-y-4">
          <Card title="Offline Transaction Query">
            <form onSubmit={handleTransactionLookup} className="flex gap-3 items-end max-w-lg">
              <div className="flex-1">
                <TextField
                  label="Transaction UUID / ID"
                  required
                  placeholder="e.g. 550e8400-e29b-41d4-a716-446655440000"
                  value={lookupId}
                  onChange={(e) => setLookupId(e.target.value)}
                />
              </div>
              <Button variant="primary" type="submit" loading={lookupLoading}>
                Lookup
              </Button>
            </form>

            {lookupResult && (
              <div className="mt-5 p-4 bg-bg border border-border rounded-[10px] space-y-2 text-[13px]">
                <h4 className="font-bold text-text">Transaction Details</h4>
                <div className="grid grid-cols-2 gap-2">
                  <span className="text-text-muted">Transaction ID:</span>
                  <span className="font-mono text-text">{lookupResult.transaction_id}</span>
                  <span className="text-text-muted">Outcome:</span>
                  <span className="font-semibold text-text">{lookupResult.result_code || lookupResult.status}</span>
                  <span className="text-text-muted">Recorded At:</span>
                  <span className="text-text">{lookupResult.client_timestamp || lookupResult.created_at}</span>
                  <span className="text-text-muted">Device / Manager:</span>
                  <span className="text-text">{lookupResult.device_id || 'Manager App'}</span>
                </div>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Conflict Review & Resolution Drawer (DEC-17) */}
      <Drawer
        isOpen={Boolean(selectedConflict)}
        onClose={() => setSelectedConflict(null)}
        title={selectedConflict ? `Conflict #${selectedConflict.conflict_id}: ${selectedConflict.conflict_type}` : 'Conflict Review'}
        subtitle={`Detected: ${selectedConflict?.detected_at ? new Date(selectedConflict.detected_at).toLocaleString() : ''}`}
        width="max-w-lg"
        footer={
          !selectedConflict?.resolved_at ? (
            <div className="flex items-center justify-between w-full">
              <Button
                variant="danger"
                onClick={() => handleResolveConflict('REJECT')}
                loading={resolving}
              >
                Reject Transaction
              </Button>

              <div className="flex items-center gap-2">
                <Button variant="secondary" onClick={() => setSelectedConflict(null)}>
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  onClick={() => handleResolveConflict('ACCEPT')}
                  loading={resolving}
                  disabled={isPeriodLocked}
                >
                  Accept Transaction
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex justify-end w-full">
              <Button variant="secondary" onClick={() => setSelectedConflict(null)}>
                Close
              </Button>
            </div>
          )
        }
      >
        {selectedConflict && (
          <div className="space-y-5 text-[13px]">
            {resolveError && (
              <Banner variant="danger" className="text-[13px]">
                {resolveError}
              </Banner>
            )}

            {/* Locked Period Refusal Warning */}
            {isPeriodLocked && (
              <div className="p-3 bg-danger-subtle border border-danger-border rounded text-danger">
                <strong>Accept Disabled:</strong> The corresponding billing period is LOCKED. Conflicts in locked periods cannot be accepted into finalized ledgers.
              </div>
            )}

            {/* Offline Transaction Information */}
            <div className="p-4 bg-bg border border-border rounded-[10px] space-y-2">
              <h4 className="font-bold text-text">Uploaded Offline Transaction</h4>
              <div className="grid grid-cols-2 gap-1.5">
                <span className="text-text-muted">Student:</span>
                <span className="font-mono font-semibold text-text">
                  {selectedConflict.transaction?.student_roll || '—'}
                </span>
                <span className="text-text-muted">Mess:</span>
                <span className="text-text">{selectedConflict.transaction?.mess_code || '—'}</span>
                <span className="text-text-muted">Recorded Scan Time:</span>
                <span className="text-text">
                  {selectedConflict.transaction?.recorded_at ? new Date(selectedConflict.transaction.recorded_at).toLocaleString() : 'N/A'}
                </span>
                <span className="text-text-muted">Manager Device:</span>
                <span className="text-text">{selectedConflict.transaction?.device_id || 'Mobile Scanner'}</span>
              </div>
            </div>

            {/* Server's Current Facts */}
            <div className="p-4 bg-surface border border-border rounded-[10px] space-y-2">
              <h4 className="font-bold text-text">Server's Current Facts</h4>
              <div className="grid grid-cols-2 gap-1.5">
                <span className="text-text-muted">Assignment Status:</span>
                <span className="text-text font-medium">
                  {selectedConflict.server_facts?.assignment_status || 'ACTIVE'}
                </span>
                <span className="text-text-muted">Active Pause on Date:</span>
                <span className={selectedConflict.server_facts?.is_paused ? 'text-warning font-bold' : 'text-text'}>
                  {selectedConflict.server_facts?.is_paused ? 'Yes (Meal Paused)' : 'No'}
                </span>
                <span className="text-text-muted">Billing Period Status:</span>
                <span className="text-text font-bold">
                  {selectedConflict.server_facts?.period_status || 'OPEN'}
                </span>
              </div>
            </div>

            {/* Resolution Form (DEC-17 mandatory notes) */}
            {!selectedConflict.resolved_at ? (
              <div className="space-y-3">
                <div className="p-3 bg-bg border border-border rounded text-[12px] text-text-secondary">
                  <strong>Policy DEC-17:</strong> Resolving a conflict requires mandatory administrative notes for auditing and ledger reconciliation.
                </div>

                <TextField
                  label="Administrative Resolution Notes"
                  required
                  placeholder="Explain why this offline transaction is accepted or rejected..."
                  value={resolveNotes}
                  onChange={(e) => setResolveNotes(e.target.value)}
                />
              </div>
            ) : (
              <div className="p-4 bg-success-subtle border border-success-border rounded-[10px] space-y-1">
                <div className="font-bold text-success">
                  Resolved as {selectedConflict.resolution}
                </div>
                <div className="text-[12px] text-text-secondary">
                  Notes: {selectedConflict.resolution_notes}
                </div>
                <div className="text-[11px] text-text-muted">
                  Resolved on: {new Date(selectedConflict.resolved_at).toLocaleString()}
                </div>
              </div>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
};

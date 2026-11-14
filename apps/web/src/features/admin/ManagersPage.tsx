import React, { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../../api/client';
import { Card } from '../../components/Card';
import { DataTable, Column } from '../../components/DataTable';
import { Button } from '../../components/Button';
import { Drawer } from '../../components/Drawer';
import { TextField } from '../../components/TextField';
import { Select } from '../../components/Select';
import { StatusBadge } from '../../components/StatusBadge';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Banner } from '../../components/Banner';
import { Icons } from '../../components/Icons';

interface ManagerItem {
  user_id: number;
  email: string;
  full_name: string;
  phone_number?: string;
  mess?: {
    id: number;
    code: string;
    name: string;
  };
  assignment_id?: number;
  is_active: boolean;
  assigned_at?: string;
  device?: {
    platform: string;
    app_version: string;
    last_sync?: string;
  };
}

interface MessOption {
  mess_id: number;
  code: string;
  name: string;
}

export const ManagersPage: React.FC = () => {
  const [managers, setManagers] = useState<ManagerItem[]>([]);
  const [messes, setMesses] = useState<MessOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Create Modal
  const [createOpen, setCreateOpen] = useState(false);
  const [formName, setFormName] = useState('');
  const [formEmail, setFormEmail] = useState('');
  const [formPhone, setFormPhone] = useState('');
  const [formMessCode, setFormMessCode] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Reassign Modal
  const [reassigningManager, setReassigningManager] = useState<ManagerItem | null>(null);
  const [reassignMessCode, setReassignMessCode] = useState('');
  const [reassignLoading, setReassignLoading] = useState(false);

  // Deactivate Modal
  const [deactivatingManager, setDeactivatingManager] = useState<ManagerItem | null>(null);
  const [deactivateLoading, setDeactivateLoading] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [managersRes, messesRes, devicesRes] = await Promise.all([
        apiClient.get<any>('/admin/mess-managers'),
        apiClient.get<any>('/messes?status=ACTIVE').catch(() => ({ results: [] })),
        apiClient.get<any>('/admin/devices').catch(() => ({ results: [] })),
      ]);

      const managerList: ManagerItem[] = Array.isArray(managersRes)
        ? managersRes
        : managersRes?.results || [];
      const messList: MessOption[] = Array.isArray(messesRes)
        ? messesRes
        : messesRes?.results || [];
      const deviceList = Array.isArray(devicesRes) ? devicesRes : devicesRes?.results || [];

      // Map device by user_id
      const deviceMap: Record<number, any> = {};
      deviceList.forEach((d: any) => {
        if (d.user_id && d.session_status === 'ACTIVE') {
          deviceMap[d.user_id] = {
            platform: d.platform,
            app_version: d.app_version,
            last_sync: d.last_active_at,
          };
        }
      });

      const enriched = managerList.map((m) => ({
        ...m,
        device: deviceMap[m.user_id],
      }));

      setManagers(enriched);
      setMesses(messList);
    } catch (err: any) {
      setError(err?.message || 'Failed to load mess managers.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleOpenCreate = () => {
    setFormName('');
    setFormEmail('');
    setFormPhone('');
    setFormMessCode(messes[0]?.code || '');
    setFormError(null);
    setCreateOpen(true);
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!formName.trim() || !formEmail.trim() || !formMessCode) {
      setFormError('Full name, email, and assigned mess are required.');
      return;
    }

    setSubmitting(true);
    try {
      await apiClient.post('/admin/mess-managers', {
        full_name: formName.trim(),
        email: formEmail.trim(),
        phone_number: formPhone.trim(),
        mess_code: formMessCode,
      });

      setSuccessMsg(`Mess Manager "${formName.trim()}" created successfully (DEC-21).`);
      setCreateOpen(false);
      fetchData();
    } catch (err: any) {
      setFormError(err?.message || 'Failed to create mess manager.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleReassign = async () => {
    if (!reassigningManager || !reassignMessCode) return;
    setReassignLoading(true);
    try {
      await apiClient.post(`/admin/mess-managers/${reassigningManager.user_id}/reassign`, {
        mess_code: reassignMessCode,
      });
      setSuccessMsg(
        `Manager "${reassigningManager.full_name}" reassigned to mess ${reassignMessCode}. Device cache will replace on next sync.`
      );
      setReassigningManager(null);
      fetchData();
    } catch (err: any) {
      setError(err?.message || 'Failed to reassign manager.');
    } finally {
      setReassignLoading(false);
    }
  };

  const handleDeactivate = async () => {
    if (!deactivatingManager) return;
    setDeactivateLoading(true);
    try {
      await apiClient.post(`/admin/mess-managers/${deactivatingManager.user_id}/deactivate`, {});
      setSuccessMsg(`Manager assignment for "${deactivatingManager.full_name}" has been deactivated.`);
      setDeactivatingManager(null);
      fetchData();
    } catch (err: any) {
      setError(err?.message || 'Failed to deactivate manager.');
    } finally {
      setDeactivateLoading(false);
    }
  };

  const columns: Column<ManagerItem>[] = [
    {
      key: 'full_name',
      header: 'Manager Name',
      render: (row) => (
        <div>
          <div className="font-semibold text-text">{row.full_name}</div>
          <div className="text-[12px] text-text-muted">{row.email}</div>
        </div>
      ),
    },
    {
      key: 'phone_number',
      header: 'Phone',
      render: (row) => <span>{row.phone_number || '—'}</span>,
    },
    {
      key: 'mess',
      header: 'Assigned Mess (DEC-21)',
      render: (row) =>
        row.mess ? (
          <span className="font-medium text-text">
            {row.mess.name} ({row.mess.code})
          </span>
        ) : (
          <span className="text-text-muted italic">Unassigned</span>
        ),
    },
    {
      key: 'device',
      header: 'Active Device & Sync',
      render: (row) =>
        row.device ? (
          <div className="text-[12px]">
            <div className="font-medium text-text">
              {row.device.platform} (v{row.device.app_version})
            </div>
            <div className="text-text-muted">
              Last sync: {row.device.last_sync ? new Date(row.device.last_sync).toLocaleString() : 'Pending'}
            </div>
          </div>
        ) : (
          <span className="text-[12px] text-text-muted italic">No active device bound</span>
        ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) => (
        <StatusBadge
          status={row.is_active ? 'ACTIVE' : 'INACTIVE'}
        />
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'right',
      render: (row) => (
        <div className="flex items-center justify-end gap-2" onClick={(e) => e.stopPropagation()}>
          {row.is_active && (
            <>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setReassigningManager(row);
                  setReassignMessCode(row.mess?.code || messes[0]?.code || '');
                }}
                icon={<Icons.RefreshCw className="w-3.5 h-3.5" />}
              >
                Reassign
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="text-danger hover:bg-danger-subtle"
                onClick={() => setDeactivatingManager(row)}
                icon={<Icons.Trash className="w-3.5 h-3.5" />}
              >
                Deactivate
              </Button>
            </>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-5">
        <div>
          <h1 className="text-[22px] font-bold text-text">Mess Managers</h1>
          <p className="text-[13px] text-text-secondary mt-0.5">
            Manage manager accounts, DEC-21 assignments, and device sync bindings
          </p>
        </div>
        <Button
          variant="primary"
          onClick={handleOpenCreate}
          icon={<Icons.Plus className="w-4 h-4" />}
        >
          Add Mess Manager
        </Button>
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

      <Card>
        <DataTable
          columns={columns}
          data={managers}
          loading={loading}
          keyExtractor={(m) => m.user_id.toString()}
          emptyMessage="No mess managers registered yet."
        />
      </Card>

      {/* Create Manager Drawer */}
      <Drawer
        isOpen={createOpen}
        onClose={() => !submitting && setCreateOpen(false)}
        title="Add Mess Manager"
        subtitle="One mess per Manager and by default one Manager per mess (DEC-21)."
        width="max-w-md"
        footer={
          <div className="flex items-center justify-end gap-3 w-full">
            <Button
              variant="secondary"
              onClick={() => setCreateOpen(false)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleCreate}
              loading={submitting}
            >
              Create Manager
            </Button>
          </div>
        }
      >
        <form onSubmit={handleCreate} className="space-y-4">
          {formError && (
            <Banner variant="danger" className="text-[13px]">
              {formError}
            </Banner>
          )}

          <div className="p-3 bg-bg border border-border rounded text-[12px] text-text-secondary">
            <strong>Policy DEC-21:</strong> Each manager is bound to a single mess hall. Their mobile app will cache attendance rosters and configuration specifically for this mess.
          </div>

          <TextField
            label="Full Name"
            required
            value={formName}
            onChange={(e) => setFormName(e.target.value)}
            placeholder="e.g. Anand Sharma"
          />

          <TextField
            label="Email Address"
            type="email"
            required
            value={formEmail}
            onChange={(e) => setFormEmail(e.target.value)}
            placeholder="e.g. anand.manager@college.edu"
          />

          <TextField
            label="Phone Number"
            value={formPhone}
            onChange={(e) => setFormPhone(e.target.value)}
            placeholder="e.g. +91 98123 45678"
          />

          <Select
            label="Assigned Mess Hall"
            required
            value={formMessCode}
            onChange={(e) => setFormMessCode(e.target.value)}
            options={messes.map((m) => ({
              value: m.code,
              label: `${m.name} (${m.code})`,
            }))}
          />
        </form>
      </Drawer>

      {/* Reassign Mess Modal with Cache Replacement Warning */}
      <ConfirmDialog
        isOpen={Boolean(reassigningManager)}
        onClose={() => setReassigningManager(null)}
        onConfirm={handleReassign}
        title={`Reassign Mess: ${reassigningManager?.full_name}`}
        description={
          <div className="space-y-3">
            <div className="p-3 bg-warning-subtle border border-warning rounded text-[13px] text-warning-text flex items-start gap-2">
              <Icons.AlertTriangle className="w-5 h-5 flex-shrink-0" />
              <div>
                <strong>Cache Replacement Warning:</strong>
                <p className="mt-0.5">
                  Reassigning this manager will invalidate their mobile SQLite cache. At the next sync, the Manager's phone will purge cached rosters and download the new mess facility's records.
                </p>
              </div>
            </div>

            <Select
              label="Select New Mess"
              value={reassignMessCode}
              onChange={(e) => setReassignMessCode(e.target.value)}
              options={messes.map((m) => ({
                value: m.code,
                label: `${m.name} (${m.code})`,
              }))}
            />
          </div>
        }
        confirmLabel="Confirm Reassignment"
        loading={reassignLoading}
      />

      {/* Deactivate Manager Modal */}
      <ConfirmDialog
        isOpen={Boolean(deactivatingManager)}
        onClose={() => setDeactivatingManager(null)}
        onConfirm={handleDeactivate}
        title={`Deactivate Manager: ${deactivatingManager?.full_name}`}
        description={`Are you sure you want to deactivate manager "${deactivatingManager?.full_name}"? Their device scanning permissions will be revoked.`}
        confirmLabel="Deactivate Manager"
        variant="danger"
        loading={deactivateLoading}
      />
    </div>
  );
};

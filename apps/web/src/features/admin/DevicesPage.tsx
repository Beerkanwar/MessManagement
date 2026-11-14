import React, { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../../api/client';
import { Card } from '../../components/Card';
import { DataTable, Column } from '../../components/DataTable';
import { Button } from '../../components/Button';
import { Select } from '../../components/Select';
import { TextField } from '../../components/TextField';
import { StatusBadge } from '../../components/StatusBadge';
import { ReasonDialog } from '../../components/ReasonDialog';
import { Banner } from '../../components/Banner';
import { Icons } from '../../components/Icons';

interface DeviceItem {
  device_registration_id: number;
  user_id: number;
  user_email: string;
  user_full_name: string;
  user_role: string;
  device_id: string;
  platform: string;
  device_name?: string;
  app_version: string;
  session_status: 'ACTIVE' | 'REVOKED' | 'PENDING_REVOCATION';
  registered_at: string;
  last_active_at?: string;
  revoked_at?: string;
  revoke_reason?: string;
}

export const DevicesPage: React.FC = () => {
  const [devices, setDevices] = useState<DeviceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Filters
  const [roleFilter, setRoleFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [search, setSearch] = useState('');

  // Revoke state with ReasonDialog & D14 rules
  const [revokingDevice, setRevokingDevice] = useState<DeviceItem | null>(null);
  const [revokeLoading, setRevokeLoading] = useState(false);

  const fetchDevices = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (roleFilter) params.set('role', roleFilter);
      if (statusFilter) params.set('status', statusFilter);
      if (search.trim()) params.set('search', search.trim());

      const res = await apiClient.get<any>(`/admin/devices?${params.toString()}`);
      const list: DeviceItem[] = Array.isArray(res) ? res : res?.results || [];
      setDevices(list);
    } catch (err: any) {
      setError(err?.message || 'Failed to load device registrations.');
    } finally {
      setLoading(false);
    }
  }, [roleFilter, statusFilter, search]);

  useEffect(() => {
    fetchDevices();
  }, [fetchDevices]);

  const handleRevokeConfirm = async (reason: string) => {
    if (!revokingDevice) return;
    setRevokeLoading(true);
    try {
      const res = await apiClient.post<any>(
        `/admin/devices/${revokingDevice.device_registration_id}/revoke`,
        { reason: reason }
      );
      setSuccessMsg(
        res?.message ||
          `Device "${revokingDevice.device_name || revokingDevice.device_id}" session revoked. Enforced D14 drain policy.`
      );
      setRevokingDevice(null);
      fetchDevices();
    } catch (err: any) {
      setError(err?.message || 'Failed to revoke device session.');
    } finally {
      setRevokeLoading(false);
    }
  };

  const columns: Column<DeviceItem>[] = [
    {
      key: 'user',
      header: 'User Account',
      render: (row) => (
        <div>
          <div className="font-semibold text-text">{row.user_full_name}</div>
          <div className="text-[12px] text-text-muted">{row.user_email}</div>
        </div>
      ),
    },
    {
      key: 'user_role',
      header: 'Role',
      render: (row) => (
        <span className="text-[12px] font-mono font-medium px-2 py-0.5 rounded bg-surface border border-border">
          {row.user_role || 'STUDENT'}
        </span>
      ),
    },
    {
      key: 'platform',
      header: 'Platform & App',
      render: (row) => (
        <div className="text-[13px]">
          <span className="font-medium text-text">{row.platform}</span>
          <span className="text-text-muted text-[12px] ml-1.5">(v{row.app_version})</span>
          {row.device_name && <div className="text-[11px] text-text-muted">{row.device_name}</div>}
        </div>
      ),
    },
    {
      key: 'registered_at',
      header: 'Registered',
      render: (row) => (
        <span className="text-[12px] text-text-secondary">
          {new Date(row.registered_at).toLocaleDateString()}
        </span>
      ),
    },
    {
      key: 'last_active_at',
      header: 'Last Sync',
      render: (row) => (
        <span className="text-[12px] text-text-secondary">
          {row.last_active_at ? new Date(row.last_active_at).toLocaleString() : 'Never'}
        </span>
      ),
    },
    {
      key: 'session_status',
      header: 'Status',
      render: (row) => (
        <StatusBadge
          status={row.session_status === 'ACTIVE' ? 'ACTIVE' : 'INACTIVE'}
        />
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'right',
      render: (row) => (
        <div className="flex items-center justify-end gap-2" onClick={(e) => e.stopPropagation()}>
          {row.session_status === 'ACTIVE' ? (
            <Button
              size="sm"
              variant="ghost"
              className="text-danger hover:bg-danger-subtle"
              onClick={() => setRevokingDevice(row)}
              icon={<Icons.Trash className="w-3.5 h-3.5" />}
            >
              Revoke Session
            </Button>
          ) : (
            <span className="text-[12px] text-text-muted italic">Revoked</span>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-5">
        <div>
          <h1 className="text-[22px] font-bold text-text">Device Registrations</h1>
          <p className="text-[13px] text-text-secondary mt-0.5">
            Monitor active mobile app sessions, sync latency, and enforce D14 device revocations
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

      <Card>
        {/* Filters */}
        <div className="p-4 grid grid-cols-1 sm:grid-cols-4 gap-4 items-center">
          <TextField
            placeholder="Search by User, Device Name, or Device ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <Select
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            options={[
              { value: '', label: 'All Roles' },
              { value: 'STUDENT', label: 'Students' },
              { value: 'MESS_MANAGER', label: 'Mess Managers' },
              { value: 'HOSTEL_CLERK', label: 'Hostel Clerks' },
            ]}
          />
          <Select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            options={[
              { value: '', label: 'All Session Statuses' },
              { value: 'ACTIVE', label: 'Active Sessions' },
              { value: 'REVOKED', label: 'Revoked Sessions' },
            ]}
          />
          <Button
            variant="secondary"
            onClick={() => {
              setSearch('');
              setRoleFilter('');
              setStatusFilter('');
            }}
          >
            Reset Filters
          </Button>
        </div>

        <DataTable
          columns={columns}
          data={devices}
          loading={loading}
          keyExtractor={(d) => d.device_registration_id.toString()}
          emptyMessage="No devices found matching filter criteria."
        />
      </Card>

      {/* Revoke ReasonDialog with D14 Policy Explanation */}
      <ReasonDialog
        isOpen={Boolean(revokingDevice)}
        onClose={() => setRevokingDevice(null)}
        onConfirm={handleRevokeConfirm}
        title={`Revoke Device: ${revokingDevice?.device_name || revokingDevice?.device_id}`}
        description="For a Student device sign-in and sync stop at once; a Manager phone with unsynced scans first becomes sync-only and is revoked when its queue is empty (D14); an offline phone keeps working until its offline window ends (up to 48 hours) [SPEC SDD §121]."
        placeholder="Enter mandatory administrative reason for device revocation..."
        confirmLabel="Revoke Device Session"
        variant="danger"
        loading={revokeLoading}
      />
    </div>
  );
};

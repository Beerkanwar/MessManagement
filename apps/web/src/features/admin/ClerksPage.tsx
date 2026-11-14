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

interface ClerkItem {
  user_id: number;
  email: string;
  full_name: string;
  phone_number?: string;
  hostel?: {
    id: number;
    code: string;
    name: string;
  };
  assignment_id?: number;
  is_active: boolean;
  assigned_at?: string;
}

interface HostelOption {
  hostel_id: number;
  code: string;
  name: string;
}

export const ClerksPage: React.FC = () => {
  const [clerks, setClerks] = useState<ClerkItem[]>([]);
  const [hostels, setHostels] = useState<HostelOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // DEC-03 Notice banner after creation
  const [createdClerkNotice, setCreatedClerkNotice] = useState<{
    email: string;
    name: string;
  } | null>(null);

  // Create Modal
  const [createOpen, setCreateOpen] = useState(false);
  const [formName, setFormName] = useState('');
  const [formEmail, setFormEmail] = useState('');
  const [formPhone, setFormPhone] = useState('');
  const [formHostelCode, setFormHostelCode] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Reassign Modal
  const [reassigningClerk, setReassigningClerk] = useState<ClerkItem | null>(null);
  const [reassignHostelCode, setReassignHostelCode] = useState('');
  const [reassignLoading, setReassignLoading] = useState(false);

  // Deactivate Modal
  const [deactivatingClerk, setDeactivatingClerk] = useState<ClerkItem | null>(null);
  const [deactivateLoading, setDeactivateLoading] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [clerksRes, hostelsRes] = await Promise.all([
        apiClient.get<any>('/admin/hostel-clerks'),
        apiClient.get<any>('/hostels?status=ACTIVE').catch(() => ({ results: [] })),
      ]);

      const clerkList: ClerkItem[] = Array.isArray(clerksRes)
        ? clerksRes
        : clerksRes?.results || [];
      const hostelList: HostelOption[] = Array.isArray(hostelsRes)
        ? hostelsRes
        : hostelsRes?.results || [];

      setClerks(clerkList);
      setHostels(hostelList);
    } catch (err: any) {
      setError(err?.message || 'Failed to load hostel clerks.');
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
    setFormHostelCode(hostels[0]?.code || '');
    setFormError(null);
    setCreateOpen(true);
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!formName.trim() || !formEmail.trim() || !formHostelCode) {
      setFormError('Full name, email, and assigned hostel are required.');
      return;
    }

    setSubmitting(true);
    try {
      await apiClient.post('/admin/hostel-clerks', {
        full_name: formName.trim(),
        email: formEmail.trim(),
        phone_number: formPhone.trim(),
        hostel_code: formHostelCode,
      });

      setCreatedClerkNotice({
        name: formName.trim(),
        email: formEmail.trim(),
      });
      setSuccessMsg(`Clerk account for "${formName.trim()}" created successfully.`);
      setCreateOpen(false);
      fetchData();
    } catch (err: any) {
      setFormError(err?.message || 'Failed to create hostel clerk.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleReassign = async () => {
    if (!reassigningClerk || !reassignHostelCode) return;
    setReassignLoading(true);
    try {
      await apiClient.post(`/admin/hostel-clerks/${reassigningClerk.user_id}/reassign`, {
        hostel_code: reassignHostelCode,
      });
      setSuccessMsg(`Clerk "${reassigningClerk.full_name}" reassigned to hostel ${reassignHostelCode}.`);
      setReassigningClerk(null);
      fetchData();
    } catch (err: any) {
      setError(err?.message || 'Failed to reassign clerk.');
    } finally {
      setReassignLoading(false);
    }
  };

  const handleDeactivate = async () => {
    if (!deactivatingClerk) return;
    setDeactivateLoading(true);
    try {
      await apiClient.post(`/admin/hostel-clerks/${deactivatingClerk.user_id}/deactivate`, {});
      setSuccessMsg(`Clerk assignment for "${deactivatingClerk.full_name}" has been deactivated.`);
      setDeactivatingClerk(null);
      fetchData();
    } catch (err: any) {
      setError(err?.message || 'Failed to deactivate clerk.');
    } finally {
      setDeactivateLoading(false);
    }
  };

  const columns: Column<ClerkItem>[] = [
    {
      key: 'full_name',
      header: 'Name',
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
      key: 'hostel',
      header: 'Assigned Hostel',
      render: (row) =>
        row.hostel ? (
          <span className="font-medium text-text">
            {row.hostel.name} ({row.hostel.code})
          </span>
        ) : (
          <span className="text-text-muted italic">Unassigned</span>
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
                  setReassigningClerk(row);
                  setReassignHostelCode(row.hostel?.code || hostels[0]?.code || '');
                }}
                icon={<Icons.RefreshCw className="w-3.5 h-3.5" />}
              >
                Reassign
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="text-danger hover:bg-danger-subtle"
                onClick={() => setDeactivatingClerk(row)}
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
          <h1 className="text-[22px] font-bold text-text">Hostel Clerks</h1>
          <p className="text-[13px] text-text-secondary mt-0.5">
            Manage clerk accounts and enforce single-hostel administrative boundaries (DEC-03)
          </p>
        </div>
        <Button
          variant="primary"
          onClick={handleOpenCreate}
          icon={<Icons.Plus className="w-4 h-4" />}
        >
          Add Hostel Clerk
        </Button>
      </div>

      {/* DEC-03 First Password Policy Notice */}
      {createdClerkNotice && (
        <div className="p-4 bg-primary-subtle border border-primary-border rounded-[10px] flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <Icons.Info className="w-5 h-5 text-primary flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="text-[14px] font-bold text-text">
                Password Setup Notice (DEC-03)
              </h4>
              <p className="text-[13px] text-text-secondary mt-1">
                Account created for <strong>{createdClerkNotice.name}</strong> ({createdClerkNotice.email}).
                Per system policy DEC-03, initial passwords are never issued in plaintext. The clerk sets their first password by clicking <strong>"Forgot password"</strong> on the web sign-in screen.
              </p>
            </div>
          </div>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setCreatedClerkNotice(null)}
          >
            Dismiss
          </Button>
        </div>
      )}

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
          data={clerks}
          loading={loading}
          keyExtractor={(c) => c.user_id.toString()}
          emptyMessage="No hostel clerks registered yet."
        />
      </Card>

      {/* Create Clerk Drawer */}
      <Drawer
        isOpen={createOpen}
        onClose={() => !submitting && setCreateOpen(false)}
        title="Add Hostel Clerk"
        subtitle="One active hostel per Clerk is strictly enforced."
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
              Create Clerk
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
            <strong>Policy DEC-03:</strong> The user will set their initial password via the "Forgot Password" link on the sign-in page using their institutional email.
          </div>

          <TextField
            label="Full Name"
            required
            value={formName}
            onChange={(e) => setFormName(e.target.value)}
            placeholder="e.g. Ramesh Kumar"
          />

          <TextField
            label="Email Address"
            type="email"
            required
            value={formEmail}
            onChange={(e) => setFormEmail(e.target.value)}
            placeholder="e.g. ramesh.clerk@college.edu"
          />

          <TextField
            label="Phone Number"
            value={formPhone}
            onChange={(e) => setFormPhone(e.target.value)}
            placeholder="e.g. +91 98765 43210"
          />

          <Select
            label="Assigned Hostel"
            required
            value={formHostelCode}
            onChange={(e) => setFormHostelCode(e.target.value)}
            options={hostels.map((h) => ({
              value: h.code,
              label: `${h.name} (${h.code})`,
            }))}
          />
        </form>
      </Drawer>

      {/* Reassign Hostel Modal */}
      <ConfirmDialog
        isOpen={Boolean(reassigningClerk)}
        onClose={() => setReassigningClerk(null)}
        onConfirm={handleReassign}
        title={`Reassign Hostel: ${reassigningClerk?.full_name}`}
        description={
          <div className="space-y-3">
            <p className="text-[13px] text-text-secondary">
              Select the new hostel for this clerk. Each clerk may only oversee a single active hostel.
            </p>
            <Select
              label="New Hostel"
              value={reassignHostelCode}
              onChange={(e) => setReassignHostelCode(e.target.value)}
              options={hostels.map((h) => ({
                value: h.code,
                label: `${h.name} (${h.code})`,
              }))}
            />
          </div>
        }
        confirmLabel="Confirm Reassignment"
        loading={reassignLoading}
      />

      {/* Deactivate Clerk Modal */}
      <ConfirmDialog
        isOpen={Boolean(deactivatingClerk)}
        onClose={() => setDeactivatingClerk(null)}
        onConfirm={handleDeactivate}
        title={`Deactivate Clerk: ${deactivatingClerk?.full_name}`}
        description={`Are you sure you want to deactivate the clerk account for "${deactivatingClerk?.full_name}"? They will lose access to verify students and manage hostel records.`}
        confirmLabel="Deactivate Account"
        variant="danger"
        loading={deactivateLoading}
      />
    </div>
  );
};

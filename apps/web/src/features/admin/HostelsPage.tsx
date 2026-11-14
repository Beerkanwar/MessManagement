import React, { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../../api/client';
import { Card } from '../../components/Card';
import { DataTable, Column } from '../../components/DataTable';
import { Button } from '../../components/Button';
import { Drawer } from '../../components/Drawer';
import { TextField } from '../../components/TextField';
import { StatusBadge } from '../../components/StatusBadge';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Banner } from '../../components/Banner';
import { Icons } from '../../components/Icons';

interface HostelItem {
  hostel_id: number;
  code: string;
  name: string;
  address?: string;
  status: 'ACTIVE' | 'INACTIVE';
  version: number;
  created_at?: string;
  active_students?: number;
  clerk_name?: string;
}

export const HostelsPage: React.FC = () => {
  const [hostels, setHostels] = useState<HostelItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Drawer state for Create / Edit
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingHostel, setEditingHostel] = useState<HostelItem | null>(null);
  const [formCode, setFormCode] = useState('');
  const [formName, setFormName] = useState('');
  const [formAddress, setFormAddress] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Deactivate state
  const [deactivatingHostel, setDeactivatingHostel] = useState<HostelItem | null>(null);
  const [deactivateLoading, setDeactivateLoading] = useState(false);
  const [deactivateRefusal, setDeactivateRefusal] = useState<string | null>(null);

  // Optimistic concurrency version conflict prompt
  const [versionConflict, setVersionConflict] = useState(false);

  const fetchHostels = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [hostelRes, clerkRes] = await Promise.all([
        apiClient.get<any>('/hostels'),
        apiClient.get<any>('/admin/hostel-clerks').catch(() => ({ results: [] })),
      ]);

      const hostelList: HostelItem[] = Array.isArray(hostelRes)
        ? hostelRes
        : hostelRes?.results || [];

      const clerkList = Array.isArray(clerkRes) ? clerkRes : clerkRes?.results || [];

      // Map clerks to hostels
      const clerkMap: Record<number, string> = {};
      clerkList.forEach((c: any) => {
        if (c.is_active && c.hostel?.id) {
          clerkMap[c.hostel.id] = c.full_name;
        }
      });

      const enriched = hostelList.map((h) => ({
        ...h,
        clerk_name: clerkMap[h.hostel_id] || 'Unassigned',
      }));

      setHostels(enriched);
    } catch (err: any) {
      setError(err?.message || 'Failed to load hostels.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHostels();
  }, [fetchHostels]);

  const handleOpenCreate = () => {
    setEditingHostel(null);
    setFormCode('');
    setFormName('');
    setFormAddress('');
    setFormError(null);
    setVersionConflict(false);
    setDrawerOpen(true);
  };

  const handleOpenEdit = (hostel: HostelItem) => {
    setEditingHostel(hostel);
    setFormCode(hostel.code);
    setFormName(hostel.name);
    setFormAddress(hostel.address || '');
    setFormError(null);
    setVersionConflict(false);
    setDrawerOpen(true);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setVersionConflict(false);

    if (!formName.trim()) {
      setFormError('Hostel display name is required.');
      return;
    }
    if (!editingHostel && !formCode.trim()) {
      setFormError('Unique hostel code is required.');
      return;
    }

    setSubmitting(true);
    try {
      if (editingHostel) {
        await apiClient.patch(`/hostels/${editingHostel.hostel_id}`, {
          name: formName.trim(),
          address: formAddress.trim(),
          version: editingHostel.version,
        });
        setSuccessMsg(`Hostel "${editingHostel.code}" updated successfully.`);
      } else {
        await apiClient.post('/hostels', {
          code: formCode.trim().toUpperCase(),
          name: formName.trim(),
          address: formAddress.trim(),
        });
        setSuccessMsg(`Hostel "${formCode.trim().toUpperCase()}" created successfully.`);
      }
      setDrawerOpen(false);
      fetchHostels();
    } catch (err: any) {
      if (err?.status === 409 || err?.code === 'OPTIMISTIC_LOCK_ERROR') {
        setVersionConflict(true);
        setFormError(
          'This hostel was modified by another administrator. Please refresh to load the latest version.'
        );
      } else {
        setFormError(err?.message || 'An error occurred while saving hostel.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeactivate = async () => {
    if (!deactivatingHostel) return;
    setDeactivateLoading(true);
    setDeactivateRefusal(null);

    try {
      await apiClient.post(`/hostels/${deactivatingHostel.hostel_id}/deactivate`, {
        version: deactivatingHostel.version,
      });
      setSuccessMsg(`Hostel "${deactivatingHostel.code}" has been deactivated.`);
      setDeactivatingHostel(null);
      fetchHostels();
    } catch (err: any) {
      if (err?.code === 'STATE_CONFLICT' || err?.status === 400) {
        setDeactivateRefusal(
          err?.message ||
            'Cannot deactivate hostel while active student assignments or an assigned Clerk exist.'
        );
      } else if (err?.status === 409) {
        setDeactivateRefusal('Version conflict: Hostel data was modified. Please reload.');
      } else {
        setDeactivateRefusal(err?.message || 'Failed to deactivate hostel.');
      }
    } finally {
      setDeactivateLoading(false);
    }
  };

  const columns: Column<HostelItem>[] = [
    {
      key: 'code',
      header: 'Code',
      render: (row) => <span className="font-mono font-bold text-text">{row.code}</span>,
    },
    {
      key: 'name',
      header: 'Hostel Name',
      render: (row) => (
        <div>
          <div className="font-medium text-text">{row.name}</div>
          {row.address && <div className="text-[12px] text-text-muted">{row.address}</div>}
        </div>
      ),
    },
    {
      key: 'clerk_name',
      header: 'Hostel Clerk',
      render: (row) => (
        <span className={row.clerk_name === 'Unassigned' ? 'text-text-muted italic' : 'text-text'}>
          {row.clerk_name}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) => (
        <StatusBadge
          status={row.status === 'ACTIVE' ? 'ACTIVE' : 'INACTIVE'}
        />
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
            onClick={() => handleOpenEdit(row)}
            icon={<Icons.Edit className="w-4 h-4" />}
          >
            Edit
          </Button>
          {row.status === 'ACTIVE' && (
            <Button
              size="sm"
              variant="ghost"
              className="text-danger hover:bg-danger-subtle"
              onClick={() => {
                setDeactivateRefusal(null);
                setDeactivatingHostel(row);
              }}
              icon={<Icons.Trash className="w-4 h-4" />}
            >
              Deactivate
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
          <h1 className="text-[22px] font-bold text-text">Hostels Master</h1>
          <p className="text-[13px] text-text-secondary mt-0.5">
            Configure campus hostel properties, clerk bindings, and status
          </p>
        </div>
        <Button
          variant="primary"
          onClick={handleOpenCreate}
          icon={<Icons.Plus className="w-4 h-4" />}
        >
          Add Hostel
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
          data={hostels}
          loading={loading}
          keyExtractor={(h) => h.hostel_id.toString()}
          emptyMessage="No hostels found. Click 'Add Hostel' to create one."
          onRowClick={(row) => handleOpenEdit(row)}
        />
      </Card>

      {/* Create / Edit Drawer */}
      <Drawer
        isOpen={drawerOpen}
        onClose={() => !submitting && setDrawerOpen(false)}
        title={editingHostel ? `Edit Hostel: ${editingHostel.code}` : 'Add New Hostel'}
        subtitle="Hostel codes are unique and cannot be modified after creation."
        width="max-w-md"
        footer={
          <div className="flex items-center justify-end gap-3 w-full">
            <Button
              variant="secondary"
              onClick={() => setDrawerOpen(false)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleSave}
              loading={submitting}
            >
              {editingHostel ? 'Save Changes' : 'Create Hostel'}
            </Button>
          </div>
        }
      >
        <form onSubmit={handleSave} className="space-y-4">
          {formError && (
            <Banner variant="danger" className="text-[13px]">
              {formError}
            </Banner>
          )}

          {versionConflict && (
            <div className="p-3 bg-warning-subtle border border-warning rounded text-[13px] text-warning-text flex items-start gap-2">
              <Icons.AlertTriangle className="w-5 h-5 flex-shrink-0" />
              <div>
                <strong>Version Conflict:</strong> Another admin saved changes to this hostel.
                <button
                  type="button"
                  onClick={() => {
                    setDrawerOpen(false);
                    fetchHostels();
                  }}
                  className="block mt-1 font-semibold text-primary underline"
                >
                  Reload latest data
                </button>
              </div>
            </div>
          )}

          <TextField
            label="Hostel Code"
            required
            disabled={Boolean(editingHostel)}
            value={formCode}
            onChange={(e) => setFormCode(e.target.value.toUpperCase())}
            placeholder="e.g. H1, H2, BH-A"
            helperText={
              editingHostel
                ? 'Hostel codes are immutable to protect student assignment records.'
                : 'Short unique identifier for the hostel (e.g. H1).'
            }
          />

          <TextField
            label="Hostel Name"
            required
            value={formName}
            onChange={(e) => setFormName(e.target.value)}
            placeholder="e.g. Himalaya Hostel"
          />

          <TextField
            label="Address / Location"
            value={formAddress}
            onChange={(e) => setFormAddress(e.target.value)}
            placeholder="e.g. North Campus, Sector 4"
          />
        </form>
      </Drawer>

      {/* Deactivate Guard Modal */}
      <ConfirmDialog
        isOpen={Boolean(deactivatingHostel)}
        onClose={() => {
          setDeactivatingHostel(null);
          setDeactivateRefusal(null);
        }}
        onConfirm={handleDeactivate}
        title={`Deactivate Hostel: ${deactivatingHostel?.code}`}
        description={
          deactivateRefusal ? (
            <div className="space-y-3">
              <div className="p-3 bg-danger-subtle border border-danger-border rounded text-[13px] text-danger">
                <strong>Deactivation Refused:</strong>
                <p className="mt-1">{deactivateRefusal}</p>
              </div>
              <p className="text-[13px] text-text-secondary">
                To deactivate this hostel, all active student assignments must first be transferred, and any assigned Clerk must be reassigned or deactivated.
              </p>
            </div>
          ) : (
            `Are you sure you want to deactivate hostel "${deactivatingHostel?.name}" (${deactivatingHostel?.code})? Deactivation will prevent new assignments.`
          )
        }
        confirmLabel={deactivateRefusal ? 'Try Again' : 'Deactivate Hostel'}
        variant="danger"
        loading={deactivateLoading}
      />
    </div>
  );
};

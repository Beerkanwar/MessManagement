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

interface MessItem {
  mess_id: number;
  code: string;
  name: string;
  status: 'ACTIVE' | 'INACTIVE';
  version: number;
  created_at?: string;
  manager_name?: string;
  manager_phone?: string;
  hostels_served?: string;
  active_students_count?: number;
}

export const MessesPage: React.FC = () => {
  const [messes, setMesses] = useState<MessItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Drawer state for Create / Edit
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingMess, setEditingMess] = useState<MessItem | null>(null);
  const [formCode, setFormCode] = useState('');
  const [formName, setFormName] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Deactivate state
  const [deactivatingMess, setDeactivatingMess] = useState<MessItem | null>(null);
  const [deactivateLoading, setDeactivateLoading] = useState(false);
  const [deactivateRefusal, setDeactivateRefusal] = useState<string | null>(null);

  // Version conflict state
  const [versionConflict, setVersionConflict] = useState(false);

  const fetchMesses = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [messRes, managerRes, hostelRes] = await Promise.all([
        apiClient.get<any>('/messes'),
        apiClient.get<any>('/admin/mess-managers').catch(() => ({ results: [] })),
        apiClient.get<any>('/hostels').catch(() => ({ results: [] })),
      ]);

      const messList: MessItem[] = Array.isArray(messRes) ? messRes : messRes?.results || [];
      const managerList = Array.isArray(managerRes) ? managerRes : managerRes?.results || [];
      const hostelList = Array.isArray(hostelRes) ? hostelRes : hostelRes?.results || [];

      const managerMap: Record<number, { name: string; phone?: string }> = {};
      managerList.forEach((m: any) => {
        if (m.is_active && m.mess?.id) {
          managerMap[m.mess.id] = { name: m.full_name, phone: m.phone_number };
        }
      });

      // Show which hostels feed the mess (by default all active hostels or mapped)
      const activeHostelCodes = hostelList
        .filter((h: any) => h.status === 'ACTIVE')
        .map((h: any) => h.code)
        .join(', ');

      const enriched = messList.map((m) => ({
        ...m,
        manager_name: managerMap[m.mess_id]?.name || 'Unassigned',
        manager_phone: managerMap[m.mess_id]?.phone || '',
        hostels_served: activeHostelCodes || 'Campus-wide',
      }));

      setMesses(enriched);
    } catch (err: any) {
      setError(err?.message || 'Failed to load messes.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMesses();
  }, [fetchMesses]);

  const handleOpenCreate = () => {
    setEditingMess(null);
    setFormCode('');
    setFormName('');
    setFormError(null);
    setVersionConflict(false);
    setDrawerOpen(true);
  };

  const handleOpenEdit = (mess: MessItem) => {
    setEditingMess(mess);
    setFormCode(mess.code);
    setFormName(mess.name);
    setFormError(null);
    setVersionConflict(false);
    setDrawerOpen(true);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setVersionConflict(false);

    if (!formName.trim()) {
      setFormError('Mess hall display name is required.');
      return;
    }
    if (!editingMess && !formCode.trim()) {
      setFormError('Unique mess code is required.');
      return;
    }

    setSubmitting(true);
    try {
      if (editingMess) {
        // Backend supports PUT or PATCH
        await apiClient.put(`/messes/${editingMess.mess_id}`, {
          name: formName.trim(),
          version: editingMess.version,
        });
        setSuccessMsg(`Mess "${editingMess.code}" updated successfully.`);
      } else {
        await apiClient.post('/messes', {
          code: formCode.trim().toUpperCase(),
          name: formName.trim(),
        });
        setSuccessMsg(`Mess "${formCode.trim().toUpperCase()}" created successfully.`);
      }
      setDrawerOpen(false);
      fetchMesses();
    } catch (err: any) {
      if (err?.status === 409 || err?.code === 'OPTIMISTIC_LOCK_ERROR') {
        setVersionConflict(true);
        setFormError('This mess was modified by another administrator. Please refresh.');
      } else {
        setFormError(err?.message || 'Failed to save mess.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeactivate = async () => {
    if (!deactivatingMess) return;
    setDeactivateLoading(true);
    setDeactivateRefusal(null);

    try {
      await apiClient.post(`/messes/${deactivatingMess.mess_id}/deactivate`, {
        version: deactivatingMess.version,
      });
      setSuccessMsg(`Mess "${deactivatingMess.code}" has been deactivated.`);
      setDeactivatingMess(null);
      fetchMesses();
    } catch (err: any) {
      if (err?.code === 'STATE_CONFLICT' || err?.status === 400) {
        setDeactivateRefusal(
          err?.message ||
            'Cannot deactivate mess: there are still ACTIVE student dining assignments.'
        );
      } else if (err?.status === 409) {
        setDeactivateRefusal('Version conflict: Mess data was modified. Please reload.');
      } else {
        setDeactivateRefusal(err?.message || 'Failed to deactivate mess.');
      }
    } finally {
      setDeactivateLoading(false);
    }
  };

  const columns: Column<MessItem>[] = [
    {
      key: 'code',
      header: 'Code',
      render: (row) => <span className="font-mono font-bold text-text">{row.code}</span>,
    },
    {
      key: 'name',
      header: 'Mess Hall Name',
      render: (row) => <span className="font-medium text-text">{row.name}</span>,
    },
    {
      key: 'manager_name',
      header: 'Manager',
      render: (row) => (
        <div>
          <div className={row.manager_name === 'Unassigned' ? 'text-text-muted italic' : 'text-text font-medium'}>
            {row.manager_name}
          </div>
          {row.manager_phone && (
            <div className="text-[12px] text-text-muted">{row.manager_phone}</div>
          )}
        </div>
      ),
    },
    {
      key: 'hostels_served',
      header: 'Feeding Hostels',
      render: (row) => (
        <span className="text-[12px] text-text-secondary bg-surface-hover px-2 py-1 rounded">
          {row.hostels_served || 'All Active'}
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
                setDeactivatingMess(row);
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
          <h1 className="text-[22px] font-bold text-text">Messes Master</h1>
          <p className="text-[13px] text-text-secondary mt-0.5">
            Manage mess facilities, manager assignments, and dining allocations
          </p>
        </div>
        <Button
          variant="primary"
          onClick={handleOpenCreate}
          icon={<Icons.Plus className="w-4 h-4" />}
        >
          Add Mess
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
          data={messes}
          loading={loading}
          keyExtractor={(m) => m.mess_id.toString()}
          emptyMessage="No mess facilities registered yet."
          onRowClick={(row) => handleOpenEdit(row)}
        />
      </Card>

      {/* Create / Edit Drawer */}
      <Drawer
        isOpen={drawerOpen}
        onClose={() => !submitting && setDrawerOpen(false)}
        title={editingMess ? `Edit Mess: ${editingMess.code}` : 'Add New Mess'}
        subtitle="Mess codes must be unique and cannot be modified once created."
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
              {editingMess ? 'Save Changes' : 'Create Mess'}
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
                <strong>Version Conflict:</strong> Mess details were updated by another administrator.
                <button
                  type="button"
                  onClick={() => {
                    setDrawerOpen(false);
                    fetchMesses();
                  }}
                  className="block mt-1 font-semibold text-primary underline"
                >
                  Reload latest data
                </button>
              </div>
            </div>
          )}

          <TextField
            label="Mess Code"
            required
            disabled={Boolean(editingMess)}
            value={formCode}
            onChange={(e) => setFormCode(e.target.value.toUpperCase())}
            placeholder="e.g. M1, M2, SOUTH-MESS"
            helperText={
              editingMess
                ? 'Mess codes are permanent to preserve student dining ledgers.'
                : 'Short unique identifier for the mess facility (e.g. M1).'
            }
          />

          <TextField
            label="Mess Name"
            required
            value={formName}
            onChange={(e) => setFormName(e.target.value)}
            placeholder="e.g. North Dining Hall"
          />
        </form>
      </Drawer>

      {/* Deactivate Modal */}
      <ConfirmDialog
        isOpen={Boolean(deactivatingMess)}
        onClose={() => {
          setDeactivatingMess(null);
          setDeactivateRefusal(null);
        }}
        onConfirm={handleDeactivate}
        title={`Deactivate Mess: ${deactivatingMess?.code}`}
        description={
          deactivateRefusal ? (
            <div className="space-y-3">
              <div className="p-3 bg-danger-subtle border border-danger-border rounded text-[13px] text-danger">
                <strong>Deactivation Refused:</strong>
                <p className="mt-1">{deactivateRefusal}</p>
              </div>
              <p className="text-[13px] text-text-secondary">
                To deactivate this mess, all active student assignments must first be transferred to another mess facility.
              </p>
            </div>
          ) : (
            `Are you sure you want to deactivate mess "${deactivatingMess?.name}" (${deactivatingMess?.code})? Deactivation will prevent meal scans and assignments.`
          )
        }
        confirmLabel={deactivateRefusal ? 'Try Again' : 'Deactivate Mess'}
        variant="danger"
        loading={deactivateLoading}
      />
    </div>
  );
};

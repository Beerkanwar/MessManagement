import React, { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../../api/client';
import { Card } from '../../components/Card';
import { DataTable, Column } from '../../components/DataTable';
import { Button } from '../../components/Button';
import { Drawer } from '../../components/Drawer';
import { TextField } from '../../components/TextField';
import { Select } from '../../components/Select';
import { Tabs } from '../../components/Tabs';
import { ReasonDialog } from '../../components/ReasonDialog';
import { Banner } from '../../components/Banner';
import { Icons } from '../../components/Icons';

interface SystemSetting {
  setting_id?: number;
  key: string;
  value: string;
  data_type: 'INTEGER' | 'DECIMAL' | 'STRING' | 'BOOLEAN' | 'JSON';
  description?: string;
  is_sensitive: boolean;
  effective_from?: string;
  group?: string;
}

interface AppVersionPolicy {
  policy_id: number;
  platform: 'ANDROID' | 'IOS';
  app_version: string;
  status: 'SUPPORTED' | 'DEPRECATED' | 'BLOCKED';
  force_update_message?: string;
  updated_at?: string;
}

interface RotationRecord {
  student_id: number;
  version: number;
  rotated_at: string;
  status: string;
}

export const SystemConfigPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'settings' | 'versions' | 'secrets'>('settings');
  const [settings, setSettings] = useState<SystemSetting[]>([]);
  const [versionPolicies, setVersionPolicies] = useState<AppVersionPolicy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Setting edit drawer
  const [editingSetting, setEditingSetting] = useState<SystemSetting | null>(null);
  const [editValue, setEditValue] = useState('');
  const [editReason, setEditReason] = useState('');
  const [settingSubmitting, setSettingSubmitting] = useState(false);
  const [settingError, setSettingError] = useState<string | null>(null);

  // App version policy modal/drawer
  const [versionDrawerOpen, setVersionDrawerOpen] = useState(false);
  const [formPlatform, setFormPlatform] = useState<'ANDROID' | 'IOS'>('ANDROID');
  const [formAppVersion, setFormAppVersion] = useState('');
  const [formPolicyStatus, setFormPolicyStatus] = useState<'SUPPORTED' | 'DEPRECATED' | 'BLOCKED'>('SUPPORTED');
  const [formForceMsg, setFormForceMsg] = useState('');
  const [versionSubmitting, setVersionSubmitting] = useState(false);

  // Secret rotation state
  const [rotateScope, setRotateScope] = useState<'MESS' | 'HOSTEL' | 'STUDENT'>('MESS');
  const [rotateTargetId, setRotateTargetId] = useState('');
  const [messes, setMesses] = useState<any[]>([]);
  const [hostels, setHostels] = useState<any[]>([]);
  const [rotateReasonOpen, setRotateReasonOpen] = useState(false);
  const [rotateLoading, setRotateLoading] = useState(false);
  const [recentRotations, setRecentRotations] = useState<RotationRecord[]>([]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [settingsRes, versionsRes, messesRes, hostelsRes] = await Promise.all([
        apiClient.get<any>('/admin/settings'),
        apiClient.get<any>('/admin/app-versions').catch(() => []),
        apiClient.get<any>('/messes').catch(() => ({ results: [] })),
        apiClient.get<any>('/hostels').catch(() => ({ results: [] })),
      ]);

      const sList: SystemSetting[] = Array.isArray(settingsRes)
        ? settingsRes
        : settingsRes?.results || [];
      const vList: AppVersionPolicy[] = Array.isArray(versionsRes)
        ? versionsRes
        : versionsRes?.results || [];

      // Group settings by domain
      const grouped = sList.map((s) => {
        let grp = 'General';
        const k = s.key.toLowerCase();
        if (k.includes('auth') || k.includes('jwt') || k.includes('token') || k.includes('session')) grp = 'Authentication';
        else if (k.includes('qr') || k.includes('time') || k.includes('drift')) grp = 'QR & Monotonic Time';
        else if (k.includes('offline') || k.includes('grace')) grp = 'Offline Operation';
        else if (k.includes('bill') || k.includes('rate') || k.includes('diet')) grp = 'Billing & Rates';
        else if (k.includes('pause') || k.includes('meal')) grp = 'Pause & Meals';
        else if (k.includes('sync') || k.includes('batch')) grp = 'Synchronization';
        else if (k.includes('import')) grp = 'Import Pipeline';
        return { ...s, group: grp };
      });

      setSettings(grouped);
      setVersionPolicies(vList);
      setMesses(Array.isArray(messesRes) ? messesRes : messesRes?.results || []);
      setHostels(Array.isArray(hostelsRes) ? hostelsRes : hostelsRes?.results || []);
    } catch (err: any) {
      setError(err?.message || 'Failed to load system configuration.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleOpenEditSetting = (s: SystemSetting) => {
    setEditingSetting(s);
    setEditValue(s.is_sensitive ? '' : s.value);
    setEditReason('');
    setSettingError(null);
  };

  const handleSaveSetting = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingSetting) return;
    setSettingError(null);

    if (!editReason.trim()) {
      setSettingError('Administrative reason is required for auditing.');
      return;
    }

    setSettingSubmitting(true);
    try {
      await apiClient.patch('/admin/settings', {
        key: editingSetting.key,
        value: editValue,
        reason: editReason.trim(),
      });
      setSuccessMsg(`Setting "${editingSetting.key}" updated.`);
      setEditingSetting(null);
      fetchData();
    } catch (err: any) {
      setSettingError(err?.message || 'Failed to update system setting.');
    } finally {
      setSettingSubmitting(false);
    }
  };

  const handleSaveVersionPolicy = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formAppVersion.trim()) return;
    setVersionSubmitting(true);
    try {
      await apiClient.post('/admin/app-versions', {
        platform: formPlatform,
        app_version: formAppVersion.trim(),
        status: formPolicyStatus,
        force_update_message: formForceMsg.trim(),
      });
      setSuccessMsg(`Version policy for ${formPlatform} v${formAppVersion.trim()} saved.`);
      setVersionDrawerOpen(false);
      fetchData();
    } catch (err: any) {
      setError(err?.message || 'Failed to save version policy.');
    } finally {
      setVersionSubmitting(false);
    }
  };

  const handleConfirmSecretRotation = async (reason: string) => {
    setRotateLoading(true);
    try {
      const payload: any = { reason: reason };
      if (rotateScope === 'MESS') payload.mess_id = parseInt(rotateTargetId);
      if (rotateScope === 'HOSTEL') payload.hostel_id = parseInt(rotateTargetId);
      if (rotateScope === 'STUDENT') payload.student_id = parseInt(rotateTargetId);

      const res = await apiClient.post<any>('/rotate', payload);
      setSuccessMsg(
        res?.message || `Successfully rotated StudentSecretKey for scope ${rotateScope}.`
      );
      setRecentRotations(res?.rotations || []);
      setRotateReasonOpen(false);
    } catch (err: any) {
      setError(err?.message || 'Failed to rotate student secrets.');
    } finally {
      setRotateLoading(false);
    }
  };

  const settingColumns: Column<SystemSetting>[] = [
    {
      key: 'key',
      header: 'Setting Key',
      render: (row) => (
        <div>
          <span className="font-mono font-bold text-text">{row.key}</span>
          {row.description && <div className="text-[12px] text-text-muted">{row.description}</div>}
        </div>
      ),
    },
    {
      key: 'group',
      header: 'Domain Group',
      render: (row) => (
        <span className="text-[12px] px-2 py-0.5 rounded bg-surface border border-border">
          {row.group}
        </span>
      ),
    },
    {
      key: 'value',
      header: 'Configured Value',
      render: (row) => (
        <span className="font-mono text-text">
          {row.is_sensitive ? '•••••••• (Sensitive)' : row.value}
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
          onClick={() => handleOpenEditSetting(row)}
          icon={<Icons.Edit className="w-3.5 h-3.5" />}
        >
          Edit
        </Button>
      ),
    },
  ];

  const versionColumns: Column<AppVersionPolicy>[] = [
    {
      key: 'platform',
      header: 'Platform',
      render: (row) => <span className="font-semibold text-text">{row.platform}</span>,
    },
    {
      key: 'app_version',
      header: 'Version',
      render: (row) => <span className="font-mono font-bold text-text">v{row.app_version}</span>,
    },
    {
      key: 'status',
      header: 'Policy Status',
      render: (row) => (
        <span
          className={`px-2 py-0.5 rounded text-[12px] font-bold ${
            row.status === 'SUPPORTED'
              ? 'bg-success-subtle text-success'
              : row.status === 'DEPRECATED'
              ? 'bg-warning-subtle text-warning-text'
              : 'bg-danger-subtle text-danger'
          }`}
        >
          {row.status}
        </span>
      ),
    },
    {
      key: 'force_update_message',
      header: 'Client Prompt Message',
      render: (row) => (
        <span className="text-[12px] text-text-secondary">{row.force_update_message || '—'}</span>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-5">
        <div>
          <h1 className="text-[22px] font-bold text-text">System Configuration</h1>
          <p className="text-[13px] text-text-secondary mt-0.5">
            Institutional parameters (Appendix B), mobile client version enforcement, and QR secret key rotations
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
          { key: 'settings', label: 'Parameter Registry' },
          { key: 'versions', label: 'App Version Policies' },
          { key: 'secrets', label: 'Secret Management' },
        ]}
      />

      {/* TAB 1: System Settings */}
      {activeTab === 'settings' && (
        <div className="space-y-4">
          <Card title="Institutional Configuration Parameters">
            <DataTable
              columns={settingColumns}
              data={settings}
              loading={loading}
              keyExtractor={(s) => s.key}
              emptyMessage="No system settings found."
              onRowClick={(row) => handleOpenEditSetting(row)}
            />
          </Card>
        </div>
      )}

      {/* TAB 2: App Versions */}
      {activeTab === 'versions' && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <p className="text-[13px] text-text-secondary">
              Control mobile client access based on app versions (DEC-18). BLOCKED versions refuse authentication; DEPRECATED versions display dismissible upgrade banners.
            </p>
            <Button
              variant="primary"
              onClick={() => {
                setFormPlatform('ANDROID');
                setFormAppVersion('');
                setFormPolicyStatus('SUPPORTED');
                setFormForceMsg('');
                setVersionDrawerOpen(true);
              }}
              icon={<Icons.Plus className="w-4 h-4" />}
            >
              Add Version Policy
            </Button>
          </div>

          <Card title="Enforced Client Version Policies">
            <DataTable
              columns={versionColumns}
              data={versionPolicies}
              loading={loading}
              keyExtractor={(v) => v.policy_id.toString()}
              emptyMessage="No version policies configured yet."
            />
          </Card>
        </div>
      )}

      {/* TAB 3: Secret Management (DEC-13) */}
      {activeTab === 'secrets' && (
        <div className="space-y-6">
          <Card
            title="Bulk Rotate StudentSecretKey"
            subtitle="Rotate HMAC QR verification keys by Student, Hostel, or Mess (DEC-13)"
          >
            <div className="space-y-4 max-w-xl">
              <div className="p-3 bg-warning-subtle border border-warning rounded text-[13px] text-warning-text flex items-start gap-2">
                <Icons.AlertTriangle className="w-5 h-5 flex-shrink-0" />
                <div>
                  <strong>Consequence of Rotation (DEC-13):</strong> Rotating retires active secret key material. Students must connect online to fetch the new key. Scans produced with the retired secret will be flagged as sync conflicts.
                </div>
              </div>

              <div className="space-y-3">
                <Select
                  label="Rotation Scope"
                  value={rotateScope}
                  onChange={(e) => {
                    setRotateScope(e.target.value as any);
                    setRotateTargetId('');
                  }}
                  options={[
                    { value: 'MESS', label: 'By Mess Facility (All students eating at Mess)' },
                    { value: 'HOSTEL', label: 'By Hostel (All students resident in Hostel)' },
                    { value: 'STUDENT', label: 'Single Student (By Student ID)' },
                  ]}
                />

                {rotateScope === 'MESS' && (
                  <Select
                    label="Target Mess Hall"
                    value={rotateTargetId}
                    onChange={(e) => setRotateTargetId(e.target.value)}
                    options={[
                      { value: '', label: 'Select Mess Facility...' },
                      ...messes.map((m) => ({ value: m.mess_id.toString(), label: `${m.name} (${m.code})` })),
                    ]}
                  />
                )}

                {rotateScope === 'HOSTEL' && (
                  <Select
                    label="Target Hostel"
                    value={rotateTargetId}
                    onChange={(e) => setRotateTargetId(e.target.value)}
                    options={[
                      { value: '', label: 'Select Hostel...' },
                      ...hostels.map((h) => ({ value: h.hostel_id.toString(), label: `${h.name} (${h.code})` })),
                    ]}
                  />
                )}

                {rotateScope === 'STUDENT' && (
                  <TextField
                    label="Student ID"
                    placeholder="Enter Student ID (e.g. 101)"
                    value={rotateTargetId}
                    onChange={(e) => setRotateTargetId(e.target.value)}
                  />
                )}

                <div className="pt-2">
                  <Button
                    variant="danger"
                    disabled={!rotateTargetId}
                    onClick={() => setRotateReasonOpen(true)}
                    icon={<Icons.Key className="w-4 h-4" />}
                  >
                    Initiate Secret Rotation
                  </Button>
                </div>
              </div>
            </div>
          </Card>

          {recentRotations.length > 0 && (
            <Card title={`Recent Rotations (${recentRotations.length})`} subtitle="Never displays plaintext secrets [SPEC App Flow §15]">
              <div className="space-y-2 max-h-60 overflow-y-auto">
                {recentRotations.map((r, i) => (
                  <div key={i} className="p-3 bg-bg border border-border rounded flex justify-between text-[13px]">
                    <span className="font-semibold text-text">Student #{r.student_id}</span>
                    <span className="font-mono text-text">Version: v{r.version}</span>
                    <span className="text-text-muted">{new Date(r.rotated_at).toLocaleString()}</span>
                    <span className="text-success font-semibold">{r.status}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}

      {/* Edit Setting Drawer */}
      <Drawer
        isOpen={Boolean(editingSetting)}
        onClose={() => setEditingSetting(null)}
        title={editingSetting ? `Edit: ${editingSetting.key}` : 'Edit Setting'}
        subtitle="Every setting change is recorded in the immutable audit trail."
        width="max-w-md"
        footer={
          <div className="flex items-center justify-end gap-3 w-full">
            <Button variant="secondary" onClick={() => setEditingSetting(null)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={handleSaveSetting} loading={settingSubmitting}>
              Save Setting
            </Button>
          </div>
        }
      >
        {editingSetting && (
          <form onSubmit={handleSaveSetting} className="space-y-4">
            {settingError && (
              <Banner variant="danger" className="text-[13px]">
                {settingError}
              </Banner>
            )}

            <TextField
              label="Configured Value"
              required
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              helperText={`Type: ${editingSetting.data_type} ${editingSetting.is_sensitive ? '(Sensitive: audit log hides value)' : ''}`}
            />

            <TextField
              label="Mandatory Reason"
              required
              placeholder="Explain why this system parameter is being updated..."
              value={editReason}
              onChange={(e) => setEditReason(e.target.value)}
            />
          </form>
        )}
      </Drawer>

      {/* App Version Drawer */}
      <Drawer
        isOpen={versionDrawerOpen}
        onClose={() => setVersionDrawerOpen(false)}
        title="Add Application Version Policy"
        subtitle="Enforce client mobile version requirements (DEC-18)"
        width="max-w-md"
        footer={
          <div className="flex items-center justify-end gap-3 w-full">
            <Button variant="secondary" onClick={() => setVersionDrawerOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={handleSaveVersionPolicy} loading={versionSubmitting}>
              Save Policy
            </Button>
          </div>
        }
      >
        <form onSubmit={handleSaveVersionPolicy} className="space-y-4">
          <Select
            label="Mobile Platform"
            value={formPlatform}
            onChange={(e) => setFormPlatform(e.target.value as any)}
            options={[
              { value: 'ANDROID', label: 'Android' },
              { value: 'IOS', label: 'iOS' },
            ]}
          />

          <TextField
            label="Version String"
            required
            placeholder="e.g. 1.2.0"
            value={formAppVersion}
            onChange={(e) => setFormAppVersion(e.target.value)}
          />

          <Select
            label="Enforcement Status"
            value={formPolicyStatus}
            onChange={(e) => setFormPolicyStatus(e.target.value as any)}
            options={[
              { value: 'SUPPORTED', label: 'SUPPORTED (Active & Allowed)' },
              { value: 'DEPRECATED', label: 'DEPRECATED (Soft Warning Prompt)' },
              { value: 'BLOCKED', label: 'BLOCKED (Forced Upgrade Required)' },
            ]}
          />

          <TextField
            label="Force Update Message"
            placeholder="e.g. Please update to continue using the Mess app."
            value={formForceMsg}
            onChange={(e) => setFormForceMsg(e.target.value)}
          />
        </form>
      </Drawer>

      {/* Secret Rotation ReasonDialog (DEC-13) */}
      <ReasonDialog
        isOpen={rotateReasonOpen}
        onClose={() => setRotateReasonOpen(false)}
        onConfirm={handleConfirmSecretRotation}
        title="Rotate Student Secret Key"
        description="Rotating will retire the previous secret. The student's device must connect to fetch the updated QR key material (DEC-13)."
        confirmLabel="Rotate Keys"
        variant="danger"
        loading={rotateLoading}
      />
    </div>
  );
};

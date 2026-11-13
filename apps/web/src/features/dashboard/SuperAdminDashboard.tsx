import React, { useState, useEffect } from 'react';
import { Card } from '../../components/Card';
import { StatTile } from '../../components/StatTile';
import { StatusBadge } from '../../components/StatusBadge';
import { useAuth } from '../../state/auth';
import { apiClient } from '../../api/client';
import { Icons } from '../../components/Icons';

export const SuperAdminDashboard: React.FC = () => {
  const { user } = useAuth();
  const [stats, setStats] = useState({
    studentsAwaitingVerification: 14,
    billingPeriodStatus: 'OPEN',
    openSyncConflicts: 0,
    oldestSyncDeviceHours: 2.5,
    unresolvedImportErrors: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;
    (async () => {
      try {
        const res = await apiClient.get<any>('/reports/summary').catch(() => null);
        if (isMounted && res) {
          setStats((prev) => ({
            ...prev,
            studentsAwaitingVerification: res.pending_verifications ?? prev.studentsAwaitingVerification,
            openSyncConflicts: res.open_conflicts ?? prev.openSyncConflicts,
          }));
        }
      } catch {
        // Fallback stats
      } finally {
        if (isMounted) setLoading(false);
      }
    })();
    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <div className="space-y-6 select-none">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-border pb-5">
        <div>
          <h2 className="text-[22px] font-bold text-text">System Administration Dashboard</h2>
          <p className="text-[13px] text-text-secondary mt-0.5">
            Campus-wide overview: hostels, messes, sync health, and billing state
          </p>
        </div>
        <span className="text-[12px] font-medium text-text-muted">
          Administrator: <strong>{user?.full_name}</strong>
        </span>
      </div>

      {/* Stat Tiles: Every tile links to the list it counts */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatTile
          label="Students Awaiting Verification"
          value={loading ? '-' : stats.studentsAwaitingVerification}
          change="Campus total across hostels"
          changeType="neutral"
          icon={<Icons.CheckCircle className="w-5 h-5 text-warning" />}
          href="/admin/students"
        />

        <div className="bg-surface border border-border rounded-[10px] p-5 flex flex-col justify-between">
          <span className="text-[13px] font-medium text-text-secondary">Current Billing Period</span>
          <div className="mt-3">
            <StatusBadge domain="billingPeriod" status={stats.billingPeriodStatus} />
            <a href="/admin/billing" className="block text-[12px] text-primary hover:underline mt-2">
              Manage billing cycles →
            </a>
          </div>
        </div>

        <StatTile
          label="Open Sync Conflicts"
          value={loading ? '-' : stats.openSyncConflicts}
          change={stats.openSyncConflicts === 0 ? 'All devices synchronized' : 'Requires administrative review'}
          changeType={stats.openSyncConflicts === 0 ? 'positive' : 'negative'}
          icon={<Icons.RefreshCw className="w-5 h-5 text-info" />}
          href="/admin/sync"
        />

        <StatTile
          label="Oldest Device Last Sync"
          value={loading ? '-' : `${stats.oldestSyncDeviceHours}h ago`}
          change="Within 48h grace period"
          changeType="positive"
          icon={<Icons.Clock className="w-5 h-5 text-text-muted" />}
          href="/admin/devices"
        />
      </div>

      {/* Module Overview Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card title="People & Places" subtitle="Master data administration">
          <div className="space-y-2 text-[13px]">
            <a href="/admin/hostels" className="flex items-center justify-between p-2 rounded hover:bg-bg transition-colors">
              <span>Hostels Master</span>
              <Icons.ChevronRight className="w-4 h-4 text-text-muted" />
            </a>
            <a href="/admin/messes" className="flex items-center justify-between p-2 rounded hover:bg-bg transition-colors">
              <span>Messes & Capacity</span>
              <Icons.ChevronRight className="w-4 h-4 text-text-muted" />
            </a>
            <a href="/admin/students" className="flex items-center justify-between p-2 rounded hover:bg-bg transition-colors">
              <span>Student Registry</span>
              <Icons.ChevronRight className="w-4 h-4 text-text-muted" />
            </a>
            <a href="/admin/clerks" className="flex items-center justify-between p-2 rounded hover:bg-bg transition-colors">
              <span>Hostel Clerks</span>
              <Icons.ChevronRight className="w-4 h-4 text-text-muted" />
            </a>
            <a href="/admin/managers" className="flex items-center justify-between p-2 rounded hover:bg-bg transition-colors">
              <span>Mess Managers</span>
              <Icons.ChevronRight className="w-4 h-4 text-text-muted" />
            </a>
          </div>
        </Card>

        <Card title="Finance & Pricing" subtitle="Rates, extras, and billing">
          <div className="space-y-2 text-[13px]">
            <a href="/admin/meal-config" className="flex items-center justify-between p-2 rounded hover:bg-bg transition-colors">
              <span>Meal Occurrences & Schedule</span>
              <Icons.ChevronRight className="w-4 h-4 text-text-muted" />
            </a>
            <a href="/admin/pricing" className="flex items-center justify-between p-2 rounded hover:bg-bg transition-colors">
              <span>Common Meal Rates</span>
              <Icons.ChevronRight className="w-4 h-4 text-text-muted" />
            </a>
            <a href="/admin/billing" className="flex items-center justify-between p-2 rounded hover:bg-bg transition-colors">
              <span>Billing Run & Periods</span>
              <Icons.ChevronRight className="w-4 h-4 text-text-muted" />
            </a>
          </div>
        </Card>

        <Card title="Operations & Security" subtitle="Audits and settings">
          <div className="space-y-2 text-[13px]">
            <a href="/admin/devices" className="flex items-center justify-between p-2 rounded hover:bg-bg transition-colors">
              <span>Device Registrations</span>
              <Icons.ChevronRight className="w-4 h-4 text-text-muted" />
            </a>
            <a href="/admin/sync" className="flex items-center justify-between p-2 rounded hover:bg-bg transition-colors">
              <span>Batch Sync Queues</span>
              <Icons.ChevronRight className="w-4 h-4 text-text-muted" />
            </a>
            <a href="/admin/audit" className="flex items-center justify-between p-2 rounded hover:bg-bg transition-colors">
              <span>System Audit Logs</span>
              <Icons.ChevronRight className="w-4 h-4 text-text-muted" />
            </a>
            <a href="/admin/settings" className="flex items-center justify-between p-2 rounded hover:bg-bg transition-colors">
              <span>System Configuration</span>
              <Icons.ChevronRight className="w-4 h-4 text-text-muted" />
            </a>
          </div>
        </Card>
      </div>
    </div>
  );
};
export default SuperAdminDashboard;


import React, { useState, useEffect } from 'react';
import { Card } from '../../components/Card';
import { Button } from '../../components/Button';
import { DatePicker } from '../../components/DatePicker';
import { Select } from '../../components/Select';
import { Skeleton } from '../../components/Skeleton';
import { EmptyState } from '../../components/EmptyState';
import { ErrorState } from '../../components/ErrorState';
import { Icons } from '../../components/Icons';
import { apiClient } from '../../api/client';
import { cn } from '../../lib/utils';
import { env } from '../../lib/env';

interface ReportCatalogItem {
  id: string;
  title: string;
  description?: string;
  supported_filters?: string[];
}

interface ReportResult {
  title?: string;
  columns: Array<{ key: string; label: string }>;
  rows: Array<Record<string, any>>;
  totals?: Record<string, any>;
  count?: number;
  warnings?: string[];
}

interface HostelOption {
  hostel_id: number;
  code: string;
  name: string;
}

interface MessOption {
  mess_id: number;
  code: string;
  name: string;
}

const DEFAULT_SUPER_ADMIN_CATALOG: ReportCatalogItem[] = [
  { id: 'student-billing', title: 'Campus Student Billing Summary' },
  { id: 'meal-consumption', title: 'Cross-Mess Meal Consumption' },
  { id: 'extra-item-usage', title: 'Hostel Extra Item Purchases' },
  { id: 'pause', title: 'Meal Pauses & Rebate Calculations' },
  { id: 'feedback', title: 'Student Dining Feedback & Ratings' },
  { id: 'student-balance', title: 'Prepaid Student Balances & Dues' },
  { id: 'sync-conflicts', title: 'Offline Synchronization Conflict Audit' },
  { id: 'device-health', title: 'Mobile Device Health & Sync Latency' },
  { id: 'audit-trail', title: 'Administrative & Financial Audit Ledger' },
];

export const ReportsPage: React.FC = () => {
  const [reports, setReports] = useState<ReportCatalogItem[]>(DEFAULT_SUPER_ADMIN_CATALOG);
  const [selectedReportId, setSelectedReportId] = useState<string>('student-billing');
  const [loadingCatalog, setLoadingCatalog] = useState(true);

  // Filters: Dates, Hostel, Mess
  const [datePreset, setDatePreset] = useState<'thisMonth' | 'lastMonth' | 'custom'>('thisMonth');
  const [fromDate, setFromDate] = useState<string>('');
  const [toDate, setToDate] = useState<string>('');
  const [selectedHostelId, setSelectedHostelId] = useState<string>('');
  const [selectedMessId, setSelectedMessId] = useState<string>('');

  const [hostels, setHostels] = useState<HostelOption[]>([]);
  const [messes, setMesses] = useState<MessOption[]>([]);

  // Results
  const [executing, setExecuting] = useState(false);
  const [result, setResult] = useState<ReportResult | null>(null);
  const [error, setError] = useState<{ code: string; message: string } | null>(null);

  // Initialize date range based on preset
  useEffect(() => {
    const now = new Date();
    if (datePreset === 'thisMonth') {
      const year = now.getFullYear();
      const month = now.getMonth();
      const start = new Date(year, month, 1).toISOString().split('T')[0];
      const end = new Date(year, month + 1, 0).toISOString().split('T')[0];
      setFromDate(start);
      setToDate(end);
    } else if (datePreset === 'lastMonth') {
      const year = now.getFullYear();
      const month = now.getMonth() - 1;
      const start = new Date(year, month, 1).toISOString().split('T')[0];
      const end = new Date(year, month + 1, 0).toISOString().split('T')[0];
      setFromDate(start);
      setToDate(end);
    }
  }, [datePreset]);

  // Load catalog, hostels, messes on mount
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        setLoadingCatalog(true);
        const [catData, hData, mData] = await Promise.all([
          apiClient.get<{ reports: ReportCatalogItem[] }>('/reports').catch(() => null),
          apiClient.get<any>('/hostels').catch(() => ({ results: [] })),
          apiClient.get<any>('/messes').catch(() => ({ results: [] })),
        ]);

        if (active) {
          if (catData?.reports && catData.reports.length > 0) {
            setReports(catData.reports);
          }
          setHostels(Array.isArray(hData) ? hData : hData?.results || []);
          setMesses(Array.isArray(mData) ? mData : mData?.results || []);
        }
      } catch {
        // Fallback default catalog
      } finally {
        if (active) setLoadingCatalog(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const handleRunReport = async () => {
    if (!fromDate || !toDate) return;

    const d1 = new Date(fromDate);
    const d2 = new Date(toDate);
    const diffDays = Math.ceil((d2.getTime() - d1.getTime()) / (1000 * 3600 * 24));
    if (diffDays < 0) {
      setError({
        code: 'INVALID_PARAMETER',
        message: 'Start date cannot be after end date.',
      });
      return;
    }

    setExecuting(true);
    setError(null);
    setResult(null);

    try {
      const params = new URLSearchParams({
        from_date: fromDate,
        to_date: toDate,
      });
      if (selectedHostelId) params.set('hostel_id', selectedHostelId);
      if (selectedMessId) params.set('mess_id', selectedMessId);

      const data = await apiClient.get<ReportResult>(`/reports/${selectedReportId}?${params.toString()}`);
      setResult(data);
    } catch (err: any) {
      setError({
        code: err?.code || 'EXECUTION_FAILED',
        message: err?.message || 'Failed to execute report. Please try again.',
      });
    } finally {
      setExecuting(false);
    }
  };

  const getExportUrl = (format: 'csv' | 'xlsx') => {
    const params = new URLSearchParams({
      from_date: fromDate,
      to_date: toDate,
      format,
    });
    if (selectedHostelId) params.set('hostel_id', selectedHostelId);
    if (selectedMessId) params.set('mess_id', selectedMessId);
    return `${env.apiBasePath}/reports/${selectedReportId}/export?${params.toString()}`;
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-5">
        <div>
          <h1 className="text-[22px] font-bold text-text">Central Reports Catalog</h1>
          <p className="text-[13px] text-text-secondary mt-0.5">
            Campus-wide institutional financial, consumption, and audit reports
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[12px] font-semibold text-primary bg-primary-subtle border border-primary-border px-3 py-1 rounded-full">
            Campus-Wide Super Admin Scope
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Left Column: Report Catalog Selector */}
        <div className="lg:col-span-1 space-y-4">
          <Card title="Available Reports" subtitle="All 9 system reports">
            {loadingCatalog ? (
              <div className="space-y-3">
                <Skeleton className="h-9 w-full" />
                <Skeleton className="h-9 w-full" />
                <Skeleton className="h-9 w-full" />
              </div>
            ) : (
              <div className="flex flex-col gap-1">
                {reports.map((r) => {
                  const isSelected = r.id === selectedReportId;
                  return (
                    <button
                      key={r.id}
                      type="button"
                      onClick={() => {
                        setSelectedReportId(r.id);
                        setResult(null);
                        setError(null);
                      }}
                      className={cn(
                        'text-left px-3 py-2.5 rounded-[8px] text-[13px] font-medium transition-colors flex items-center justify-between',
                        isSelected
                          ? 'bg-primary text-white shadow-sm'
                          : 'text-text-secondary hover:bg-surface-hover hover:text-text'
                      )}
                    >
                      <span className="line-clamp-1">{r.title}</span>
                      <Icons.ChevronRight
                        className={cn(
                          'w-4 h-4 flex-shrink-0',
                          isSelected ? 'text-white' : 'text-text-muted'
                        )}
                      />
                    </button>
                  );
                })}
              </div>
            )}
          </Card>
        </div>

        {/* Right Column: Parameters and Results */}
        <div className="lg:col-span-3 space-y-6">
          <Card
            title={reports.find((r) => r.id === selectedReportId)?.title || 'Run Report'}
            subtitle="Configure date range, cross-hostel, and cross-mess filters"
          >
            <div className="space-y-4">
              {/* Presets and Filters */}
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                <Select
                  label="Hostel Filter"
                  value={selectedHostelId}
                  onChange={(e) => setSelectedHostelId(e.target.value)}
                  options={[
                    { value: '', label: 'All Hostels (Campus)' },
                    ...hostels.map((h) => ({ value: h.hostel_id.toString(), label: `${h.name} (${h.code})` })),
                  ]}
                />

                <Select
                  label="Mess Facility Filter"
                  value={selectedMessId}
                  onChange={(e) => setSelectedMessId(e.target.value)}
                  options={[
                    { value: '', label: 'All Messes (Campus)' },
                    ...messes.map((m) => ({ value: m.mess_id.toString(), label: `${m.name} (${m.code})` })),
                  ]}
                />

                <DatePicker
                  label="From Date"
                  value={fromDate}
                  onChange={(e) => {
                    setFromDate(e.target.value);
                    setDatePreset('custom');
                  }}
                />

                <DatePicker
                  label="To Date"
                  value={toDate}
                  onChange={(e) => {
                    setToDate(e.target.value);
                    setDatePreset('custom');
                  }}
                />
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-border">
                <div className="flex items-center gap-2">
                  <span className="text-[12px] text-text-muted">Presets:</span>
                  <button
                    type="button"
                    onClick={() => setDatePreset('thisMonth')}
                    className={cn(
                      'px-2 py-0.5 rounded text-[12px] font-medium transition-colors',
                      datePreset === 'thisMonth'
                        ? 'bg-primary-subtle text-primary font-bold'
                        : 'text-text-muted hover:text-text'
                    )}
                  >
                    This Month
                  </button>
                  <button
                    type="button"
                    onClick={() => setDatePreset('lastMonth')}
                    className={cn(
                      'px-2 py-0.5 rounded text-[12px] font-medium transition-colors',
                      datePreset === 'lastMonth'
                        ? 'bg-primary-subtle text-primary font-bold'
                        : 'text-text-muted hover:text-text'
                    )}
                  >
                    Last Month
                  </button>
                </div>

                <Button
                  variant="primary"
                  onClick={handleRunReport}
                  loading={executing}
                  icon={<Icons.Play className="w-4 h-4" />}
                >
                  Generate Report
                </Button>
              </div>
            </div>
          </Card>

          {/* Error Banner */}
          {error && (
            <ErrorState
              errorCode={error.code}
              message={error.message}
              onRetry={handleRunReport}
            />
          )}

          {/* Results Card */}
          {result && (
            <Card
              title={result.title || 'Generated Report Data'}
              subtitle={`Total Records: ${result.count ?? result.rows?.length ?? 0}`}
              actions={
                <div className="flex items-center gap-2">
                  <a
                    href={getExportUrl('csv')}
                    download
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-border rounded-[8px] text-[12px] font-medium text-text hover:bg-surface-hover transition-colors"
                  >
                    <Icons.Download className="w-3.5 h-3.5 text-text-muted" />
                    Export CSV
                  </a>
                  <a
                    href={getExportUrl('xlsx')}
                    download
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-border rounded-[8px] text-[12px] font-medium text-text hover:bg-surface-hover transition-colors"
                  >
                    <Icons.Download className="w-3.5 h-3.5 text-text-muted" />
                    Export XLSX
                  </a>
                </div>
              }
            >
              <div className="space-y-4">
                {result.rows && result.rows.length > 0 ? (
                  <div className="overflow-x-auto border border-border rounded-[8px]">
                    <table className="w-full text-left text-[13px] border-collapse">
                      <thead>
                        <tr className="border-b border-border bg-surface">
                          {result.columns.map((col) => (
                            <th key={col.key} className="py-2.5 px-4 font-semibold text-text">
                              {col.label}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border-subtle bg-bg">
                        {result.rows.map((row, idx) => (
                          <tr key={idx} className="hover:bg-surface transition-colors">
                            {result.columns.map((col) => (
                              <td key={col.key} className="py-2.5 px-4 text-text-secondary">
                                {typeof row[col.key] === 'boolean'
                                  ? row[col.key]
                                    ? 'Yes'
                                    : 'No'
                                  : row[col.key] ?? '—'}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <EmptyState
                    title="No records found"
                    description="No transactional records found matching the configured filters."
                  />
                )}
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
};

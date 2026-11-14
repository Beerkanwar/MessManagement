import React, { useState, useEffect } from 'react';
import { Card } from '../../components/Card';
import { Button } from '../../components/Button';
import { DatePicker } from '../../components/DatePicker';
import { Skeleton } from '../../components/Skeleton';
import { EmptyState } from '../../components/EmptyState';
import { ErrorState } from '../../components/ErrorState';
import { Icons } from '../../components/Icons';
import { apiClient } from '../../api/client';
import { useAuth } from '../../state/auth';
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

export const ReportsPage: React.FC = () => {
  const { assignment } = useAuth();
  const [reports, setReports] = useState<ReportCatalogItem[]>([]);
  const [selectedReportId, setSelectedReportId] = useState<string>('student-billing');
  const [loadingCatalog, setLoadingCatalog] = useState(true);

  // Filter params
  const [datePreset, setDatePreset] = useState<'thisMonth' | 'lastMonth' | 'custom'>('thisMonth');
  const [fromDate, setFromDate] = useState<string>('');
  const [toDate, setToDate] = useState<string>('');

  // Results
  const [executing, setExecuting] = useState(false);
  const [result, setResult] = useState<ReportResult | null>(null);
  const [error, setError] = useState<{ code: string; message: string; traceId?: string } | null>(null);

  // Scope chip
  const scopeLabel = assignment?.hostel_name || (assignment?.hostel_id ? `Hostel ${assignment.hostel_id}` : 'Assigned Hostel');

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

  // Load catalog on mount
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        setLoadingCatalog(true);
        const data = await apiClient.get<{ reports: ReportCatalogItem[] }>('/reports');
        if (active && data?.reports) {
          setReports(data.reports);
          if (data.reports.length > 0 && !data.reports.find((r) => r.id === selectedReportId)) {
            setSelectedReportId(data.reports[0].id);
          }
        }
      } catch {
        // Fallback default catalog for Clerk if backend catalog fails
        if (active) {
          setReports([
            { id: 'student-billing', title: 'Student Billing' },
            { id: 'meal-consumption', title: 'Meal Consumption' },
            { id: 'extra-item-usage', title: 'Extra-Item Usage' },
            { id: 'pause', title: 'Mess Pause' },
            { id: 'feedback', title: 'Student Feedback' },
            { id: 'student-balance', title: 'Student Balance' },
          ]);
        }
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

    // Check date range limitation (Custom up to 366 days)
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
    if (diffDays > 366) {
      setError({
        code: 'INVALID_PARAMETER',
        message: 'Report date range cannot exceed 366 days. Please narrow the range.',
      });
      return;
    }

    setExecuting(true);
    setError(null);
    setResult(null);

    try {
      const queryParams = new URLSearchParams({
        from: fromDate,
        to: toDate,
        format: 'json',
      });
      const data = await apiClient.get<ReportResult>(`/reports/${selectedReportId}?${queryParams.toString()}`);
      setResult(data);
    } catch (err: any) {
      setError({
        code: err.code || 'REPORT_EXECUTION_FAILED',
        message: err.message || 'Unable to generate report. Please try again.',
        traceId: err.traceId,
      });
    } finally {
      setExecuting(false);
    }
  };

  const handleExport = (format: 'csv' | 'xlsx' | 'pdf') => {
    if (!fromDate || !toDate) return;
    const queryParams = new URLSearchParams({
      from: fromDate,
      to: toDate,
      format,
    });
    const url = `${env.apiBasePath}/reports/${selectedReportId}?${queryParams.toString()}`;
    window.open(url, '_blank');
  };

  const selectedReport = reports.find((r) => r.id === selectedReportId);

  return (
    <div className="space-y-6 select-none">
      {/* Header with Scope Chip */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-5">
        <div>
          <div className="flex items-center gap-2.5">
            <h2 className="text-[22px] font-bold text-text">Reports & Exports</h2>
            <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-primary-subtle text-primary border border-primary-border">
              Scope: {scopeLabel}
            </span>
          </div>
          <p className="text-[13px] text-text-secondary mt-0.5">
            Run scoped consumption, billing, attendance, and feedback summaries.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Left: Report Catalog List */}
        <div className="lg:col-span-1 space-y-2">
          <span className="block text-[11px] font-bold text-text-muted uppercase tracking-wider px-1">
            Available Reports
          </span>
          {loadingCatalog ? (
            <div className="space-y-2">
              <Skeleton height={40} />
              <Skeleton height={40} />
              <Skeleton height={40} />
            </div>
          ) : (
            <div className="space-y-1">
              {reports.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => {
                    setSelectedReportId(r.id);
                    setResult(null);
                    setError(null);
                  }}
                  className={cn(
                    'w-full text-left px-3 py-2.5 rounded-[6px] text-[13px] font-medium transition-colors flex items-center justify-between',
                    selectedReportId === r.id
                      ? 'bg-primary text-white font-semibold'
                      : 'text-text-secondary hover:text-text hover:bg-bg border border-transparent'
                  )}
                >
                  <span>{r.title}</span>
                  <Icons.ChevronRight className="w-4 h-4 opacity-70" />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Right: Parameters & Results */}
        <div className="lg:col-span-3 space-y-6">
          <Card
            title={selectedReport?.title || 'Report Parameters'}
            subtitle="Configure date range and filters"
          >
            <div className="space-y-5">
              {/* Presets */}
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[12px] font-medium text-text-muted mr-1">Preset:</span>
                <button
                  type="button"
                  onClick={() => setDatePreset('thisMonth')}
                  className={cn(
                    'px-2.5 py-1 text-[12px] rounded-[6px] font-medium border transition-colors',
                    datePreset === 'thisMonth'
                      ? 'bg-primary text-white border-primary'
                      : 'bg-white text-text border-border hover:bg-bg'
                  )}
                >
                  This Month
                </button>
                <button
                  type="button"
                  onClick={() => setDatePreset('lastMonth')}
                  className={cn(
                    'px-2.5 py-1 text-[12px] rounded-[6px] font-medium border transition-colors',
                    datePreset === 'lastMonth'
                      ? 'bg-primary text-white border-primary'
                      : 'bg-white text-text border-border hover:bg-bg'
                  )}
                >
                  Last Month
                </button>
                <button
                  type="button"
                  onClick={() => setDatePreset('custom')}
                  className={cn(
                    'px-2.5 py-1 text-[12px] rounded-[6px] font-medium border transition-colors',
                    datePreset === 'custom'
                      ? 'bg-primary text-white border-primary'
                      : 'bg-white text-text border-border hover:bg-bg'
                  )}
                >
                  Custom Range (≤ 366 days)
                </button>
              </div>

              {/* Date pickers */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <DatePicker
                  label="From Date"
                  value={fromDate}
                  onChange={(e) => {
                    setDatePreset('custom');
                    setFromDate(e.target.value);
                  }}
                  required
                />
                <DatePicker
                  label="To Date"
                  value={toDate}
                  onChange={(e) => {
                    setDatePreset('custom');
                    setToDate(e.target.value);
                  }}
                  required
                />
              </div>

              {/* Actions & Export Buttons */}
              <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-border">
                <Button
                  variant="primary"
                  onClick={handleRunReport}
                  loading={executing}
                  icon={<Icons.Check className="w-4 h-4" />}
                >
                  Run Report
                </Button>

                <div className="flex items-center gap-2">
                  <span className="text-[12px] text-text-muted mr-1">Export:</span>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handleExport('csv')}
                    disabled={executing || !result}
                  >
                    CSV
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handleExport('xlsx')}
                    disabled={executing || !result}
                  >
                    XLSX
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handleExport('pdf')}
                    disabled={executing || !result}
                  >
                    PDF
                  </Button>
                </div>
              </div>
            </div>
          </Card>

          {/* Results Area */}
          {error && (
            <ErrorState
              errorCode={error.code}
              message={error.message}
              traceId={error.traceId}
              onRetry={handleRunReport}
            />
          )}

          {executing && (
            <div className="space-y-3 p-6 bg-surface border border-border rounded-[10px]">
              <Skeleton height={28} width="40%" />
              <Skeleton height={20} />
              <Skeleton height={20} />
              <Skeleton height={20} />
            </div>
          )}

          {!executing && !error && !result && (
            <EmptyState
              title="Report Ready to Run"
              description="Select parameters above and click 'Run Report' to preview data and enable exports."
              icon={<Icons.Calendar className="w-6 h-6 stroke-[1.5]" />}
            />
          )}

          {!executing && result && (
            <div className="space-y-4">
              <div className="border border-border rounded-[10px] bg-surface overflow-hidden">
                <div className="px-4 py-3 border-b border-border bg-bg/50 flex items-center justify-between">
                  <span className="text-[13px] font-semibold text-text">
                    Results ({result.rows?.length ?? 0} rows)
                  </span>
                  <span className="text-[11px] text-text-muted">
                    Filtered by {fromDate} to {toDate}
                  </span>
                </div>

                <div className="overflow-x-auto max-h-[500px]">
                  <table className="w-full border-collapse text-left text-[13px]">
                    <thead className="bg-bg border-b border-border-strong sticky top-0">
                      <tr>
                        {result.columns.map((col) => (
                          <th key={col.key} className="px-4 py-2.5 font-semibold text-text">
                            {col.label}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {result.rows.length === 0 ? (
                        <tr>
                          <td colSpan={result.columns.length} className="p-6 text-center text-text-muted">
                            No records found for the selected period.
                          </td>
                        </tr>
                      ) : (
                        result.rows.map((row, idx) => (
                          <tr key={idx} className="hover:bg-bg/50">
                            {result.columns.map((col) => (
                              <td key={col.key} className="px-4 py-2 text-text tabular-nums">
                                {String(row[col.key] ?? '-')}
                              </td>
                            ))}
                          </tr>
                        ))
                      )}
                    </tbody>
                    {result.totals && (
                      <tfoot className="bg-bg/80 border-t-2 border-border-strong font-bold">
                        <tr>
                          {result.columns.map((col, idx) => (
                            <td key={col.key} className="px-4 py-2.5 text-text tabular-nums">
                              {idx === 0
                                ? 'Totals'
                                : String(result.totals?.[col.key] ?? '')}
                            </td>
                          ))}
                        </tr>
                      </tfoot>
                    )}
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
export default ReportsPage;


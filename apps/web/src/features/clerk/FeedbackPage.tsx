import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Card } from '../../components/Card';
import { Button } from '../../components/Button';
import { Skeleton } from '../../components/Skeleton';
import { EmptyState } from '../../components/EmptyState';
import { ErrorState } from '../../components/ErrorState';
import { Drawer } from '../../components/Drawer';
import { apiClient } from '../../api/client';
import { useAuth } from '../../state/auth';
import { cn } from '../../lib/utils';

export interface FeedbackRow {
  feedback_id?: number;
  student: string;
  roll_number?: string;
  mess: string;
  month: string; // YYYY-MM
  food_quality_rating: number;
  taste_rating: number;
  comments: string;
  submitted_at?: string;
}

export interface FeedbackTotals {
  response_count?: number;
  average_quality?: number | string;
  average_taste?: number | string;
}

const StarIcon: React.FC<{ filled: boolean; className?: string }> = ({ filled, className }) => (
  <svg
    viewBox="0 0 24 24"
    className={cn('w-3.5 h-3.5', filled ? 'text-amber-400 fill-amber-400' : 'text-gray-300 fill-transparent', className)}
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
  </svg>
);

export const FeedbackPage: React.FC = () => {
  const { assignment } = useAuth();
  const hostelId = assignment?.hostel_id;

  // Filters
  const [selectedMonth, setSelectedMonth] = useState<string>(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  });
  const [selectedMess, setSelectedMess] = useState<string>('ALL');
  const [minRating, setMinRating] = useState<number>(1);
  const [maxRating, setMaxRating] = useState<number>(5);

  // Data
  const [rows, setRows] = useState<FeedbackRow[]>([]);
  const [totals, setTotals] = useState<FeedbackTotals | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ code: string; message: string; traceId?: string } | null>(null);

  // Selected Row for Full Comment Drawer
  const [selectedRow, setSelectedRow] = useState<FeedbackRow | null>(null);

  // Fetch Feedback via Report API
  const fetchFeedback = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [yearStr, monthStr] = selectedMonth.split('-');
      const year = parseInt(yearStr);
      const month = parseInt(monthStr);

      const from = new Date(year, month - 1, 1).toISOString().split('T')[0];
      const to = new Date(year, month, 0).toISOString().split('T')[0];

      const params = new URLSearchParams({ from, to });
      if (selectedMess !== 'ALL') {
        params.set('mess', selectedMess);
      }

      const res = await apiClient.get<any>(`/api/v1/reports/feedback?${params.toString()}`);

      const dataRows = res.rows || [];
      setRows(Array.isArray(dataRows) ? dataRows : []);
      setTotals(res.totals || null);
    } catch (err: any) {
      setError({
        code: err.code || 'LOAD_FAILED',
        message: err.message || 'Failed to load feedback records',
        traceId: err.trace_id,
      });
    } finally {
      setLoading(false);
    }
  }, [selectedMonth, selectedMess]);

  useEffect(() => {
    fetchFeedback();
  }, [fetchFeedback]);

  // Client-side filtering by rating range
  const filteredRows = useMemo(() => {
    return rows.filter((r) => {
      const avg = (r.food_quality_rating + r.taste_rating) / 2;
      return avg >= minRating && avg <= maxRating;
    });
  }, [rows, minRating, maxRating]);

  // Distinct messes from data for filter
  const messOptions = useMemo(() => {
    const set = new Set<string>();
    rows.forEach((r) => {
      if (r.mess) set.add(r.mess);
    });
    return Array.from(set);
  }, [rows]);

  const renderStars = (rating: number) => {
    return (
      <div className="flex items-center gap-0.5" aria-label={`${rating} out of 5 stars`}>
        {[1, 2, 3, 4, 5].map((star) => (
          <StarIcon key={star} filled={star <= Math.round(rating)} />
        ))}
        <span className="text-xs font-semibold text-text-primary ml-1">{rating}</span>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-bold tracking-tight text-text-primary">Student Feedback</h1>
          <span className="text-xs font-semibold px-2 py-0.5 rounded bg-surface-subtle border border-border-default text-text-secondary">
            Read-Only • Non-Anonymous
          </span>
        </div>
        <p className="text-sm text-text-secondary mt-1">
          Review monthly food quality and taste satisfaction submitted by students of{' '}
          <span className="font-semibold text-text-primary">
            {assignment?.hostel_name || (hostelId ? `Hostel ${hostelId}` : 'your hostel')}
          </span>
        </p>
      </div>

      {/* Filter Bar */}
      <Card className="bg-surface-default p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div>
            <label className="block text-xs font-semibold text-text-secondary mb-1">Month</label>
            <input
              type="month"
              value={selectedMonth}
              onChange={(e) => setSelectedMonth(e.target.value)}
              className="w-full px-3 py-1.5 text-xs border border-border-default rounded bg-surface-default text-text-primary focus:outline-none focus:ring-1 focus:ring-primary-focus"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-secondary mb-1">Mess</label>
            <select
              value={selectedMess}
              onChange={(e) => setSelectedMess(e.target.value)}
              className="w-full px-3 py-1.5 text-xs border border-border-default rounded bg-surface-default text-text-primary focus:outline-none focus:ring-1 focus:ring-primary-focus"
            >
              <option value="ALL">All Messes</option>
              {messOptions.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-secondary mb-1">Min Rating</label>
            <select
              value={minRating}
              onChange={(e) => setMinRating(parseInt(e.target.value))}
              className="w-full px-3 py-1.5 text-xs border border-border-default rounded bg-surface-default text-text-primary focus:outline-none focus:ring-1 focus:ring-primary-focus"
            >
              {[1, 2, 3, 4, 5].map((val) => (
                <option key={val} value={val}>
                  {val} {val === 1 ? 'Star' : 'Stars'} or more
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-secondary mb-1">Max Rating</label>
            <select
              value={maxRating}
              onChange={(e) => setMaxRating(parseInt(e.target.value))}
              className="w-full px-3 py-1.5 text-xs border border-border-default rounded bg-surface-default text-text-primary focus:outline-none focus:ring-1 focus:ring-primary-focus"
            >
              {[1, 2, 3, 4, 5].map((val) => (
                <option key={val} value={val}>
                  Up to {val} {val === 1 ? 'Star' : 'Stars'}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Card>

      {/* Summary Stat Tiles */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card className="bg-surface-default p-4">
          <span className="text-xs text-text-secondary font-medium">Responses Count</span>
          <p className="text-2xl font-bold text-text-primary mt-1">
            {totals?.response_count !== undefined ? totals.response_count : rows.length}
          </p>
          <span className="text-[11px] text-text-muted mt-0.5">Submitted for {selectedMonth}</span>
        </Card>

        <Card className="bg-surface-default p-4">
          <span className="text-xs text-text-secondary font-medium">Average Food Quality</span>
          <div className="flex items-center gap-2 mt-1">
            <p className="text-2xl font-bold text-primary-default">
              {totals?.average_quality !== undefined ? Number(totals.average_quality).toFixed(1) : '—'}
            </p>
            {totals?.average_quality && renderStars(Number(totals.average_quality))}
          </div>
          <span className="text-[11px] text-text-muted mt-0.5">Scale 1 (Poor) to 5 (Excellent)</span>
        </Card>

        <Card className="bg-surface-default p-4">
          <span className="text-xs text-text-secondary font-medium">Average Taste Rating</span>
          <div className="flex items-center gap-2 mt-1">
            <p className="text-2xl font-bold text-primary-default">
              {totals?.average_taste !== undefined ? Number(totals.average_taste).toFixed(1) : '—'}
            </p>
            {totals?.average_taste && renderStars(Number(totals.average_taste))}
          </div>
          <span className="text-[11px] text-text-muted mt-0.5">Scale 1 (Poor) to 5 (Excellent)</span>
        </Card>
      </div>

      {/* Error State */}
      {error && (
        <ErrorState
          errorCode={error.code}
          message={error.message}
          traceId={error.traceId}
          onRetry={fetchFeedback}
        />
      )}

      {/* Data Table */}
      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      ) : filteredRows.length === 0 ? (
        <EmptyState
          title="No feedback found"
          description={`No student feedback has been submitted for ${selectedMonth} matching your filter criteria.`}
        />
      ) : (
        <Card className="p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-border-default bg-surface-subtle text-text-secondary font-semibold">
                  <th className="py-3 px-3">Student Name</th>
                  <th className="py-3 px-3">Mess</th>
                  <th className="py-3 px-3">Month</th>
                  <th className="py-3 px-3">Food Quality</th>
                  <th className="py-3 px-3">Taste</th>
                  <th className="py-3 px-3">Comment Preview</th>
                  <th className="py-3 px-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-default">
                {filteredRows.map((r, idx) => (
                  <tr
                    key={idx}
                    onClick={() => setSelectedRow(r)}
                    className="hover:bg-surface-subtle cursor-pointer transition-colors"
                  >
                    <td className="py-3 px-3 font-semibold text-text-primary">{r.student}</td>
                    <td className="py-3 px-3 text-text-secondary">{r.mess}</td>
                    <td className="py-3 px-3 font-mono text-text-secondary">{r.month}</td>
                    <td className="py-3 px-3">{renderStars(r.food_quality_rating)}</td>
                    <td className="py-3 px-3">{renderStars(r.taste_rating)}</td>
                    <td className="py-3 px-3 text-text-secondary max-w-xs truncate">
                      {r.comments ? r.comments : <span className="text-text-muted italic">No comments</span>}
                    </td>
                    <td className="py-3 px-3 text-right">
                      <Button variant="ghost" size="sm" className="text-xs">
                        View
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Row Drawer for Full Comment */}
      {selectedRow && (
        <Drawer
          isOpen={Boolean(selectedRow)}
          onClose={() => setSelectedRow(null)}
          title={`Feedback: ${selectedRow.student}`}
        >
          <div className="space-y-6 text-sm">
            <div className="bg-surface-subtle p-3 rounded-lg border border-border-default space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-text-secondary">Student:</span>
                <span className="font-bold text-text-primary">{selectedRow.student}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Mess:</span>
                <span className="font-semibold text-text-primary">{selectedRow.mess}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Month:</span>
                <span className="font-semibold text-text-primary">{selectedRow.month}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-text-secondary">Food Quality:</span>
                <div>{renderStars(selectedRow.food_quality_rating)}</div>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-text-secondary">Taste Rating:</span>
                <div>{renderStars(selectedRow.taste_rating)}</div>
              </div>
            </div>

            <div className="space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-text-secondary">
                Student Comments (Un-truncated)
              </h4>
              <div className="p-3 bg-surface-default border border-border-default rounded-lg text-xs leading-relaxed text-text-primary whitespace-pre-wrap">
                {selectedRow.comments || <span className="text-text-muted italic">No written comments provided.</span>}
              </div>
            </div>

            <div className="pt-4 border-t border-border-default">
              <Button variant="secondary" className="w-full text-xs" onClick={() => setSelectedRow(null)}>
                Close
              </Button>
            </div>
          </div>
        </Drawer>
      )}
    </div>
  );
};

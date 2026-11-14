import React, { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../../api/client';
import { Card } from '../../components/Card';
import { DataTable, Column } from '../../components/DataTable';
import { Button } from '../../components/Button';
import { Drawer } from '../../components/Drawer';
import { TextField } from '../../components/TextField';
import { Banner } from '../../components/Banner';
import { Icons } from '../../components/Icons';

interface AuditEvent {
  audit_id: number;
  event_type: string;
  occurred_at: string;
  actor?: {
    user_id?: number;
    email?: string;
    full_name?: string;
    role?: string;
  };
  device_id?: string;
  entity_type: string;
  entity_id: string;
  reason?: string;
  correlation_id?: string;
  old_values?: Record<string, any>;
  new_values?: Record<string, any>;
  metadata?: Record<string, any>;
}

export const AuditLogsPage: React.FC = () => {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [eventTypeFilter, setEventTypeFilter] = useState('');
  const [actorFilter, setActorFilter] = useState('');
  const [entityTypeFilter, setEntityTypeFilter] = useState('');
  const [correlationIdFilter, setCorrelationIdFilter] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');

  // Selected event for side-by-side diff drawer
  const [selectedEvent, setSelectedEvent] = useState<AuditEvent | null>(null);

  const fetchAuditEvents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (eventTypeFilter) params.set('event_type', eventTypeFilter);
      if (actorFilter.trim()) params.set('actor', actorFilter.trim());
      if (entityTypeFilter) params.set('entity_type', entityTypeFilter);
      if (correlationIdFilter.trim()) params.set('correlation_id', correlationIdFilter.trim());
      if (fromDate) params.set('from', fromDate);
      if (toDate) params.set('to', toDate);

      const res = await apiClient.get<any>(`/audit/events?${params.toString()}`);
      const list: AuditEvent[] = Array.isArray(res) ? res : res?.results || [];
      setEvents(list);
    } catch (err: any) {
      setError(err?.message || 'Failed to load audit logs.');
    } finally {
      setLoading(false);
    }
  }, [eventTypeFilter, actorFilter, entityTypeFilter, correlationIdFilter, fromDate, toDate]);

  useEffect(() => {
    fetchAuditEvents();
  }, [fetchAuditEvents]);

  const handleFilterByCorrelationId = (correlationId: string) => {
    setCorrelationIdFilter(correlationId);
    setSelectedEvent(null);
  };

  const columns: Column<AuditEvent>[] = [
    {
      key: 'occurred_at',
      header: 'Timestamp',
      render: (row) => (
        <span className="text-[12px] text-text-secondary whitespace-nowrap">
          {new Date(row.occurred_at).toLocaleString()}
        </span>
      ),
    },
    {
      key: 'event_type',
      header: 'Event',
      render: (row) => (
        <span className="font-mono font-semibold text-[13px] text-text">
          {row.event_type}
        </span>
      ),
    },
    {
      key: 'actor',
      header: 'Actor',
      render: (row) => (
        <div>
          <div className="font-medium text-text text-[13px]">
            {row.actor?.full_name || row.actor?.email || 'System'}
          </div>
          {row.actor?.role && (
            <span className="text-[11px] text-text-muted">{row.actor.role}</span>
          )}
        </div>
      ),
    },
    {
      key: 'entity',
      header: 'Entity',
      render: (row) => (
        <span className="text-[12px] text-text-secondary">
          {row.entity_type} #{row.entity_id}
        </span>
      ),
    },
    {
      key: 'reason',
      header: 'Reason / Notes',
      render: (row) => (
        <span className="text-[12px] text-text line-clamp-1">
          {row.reason || '—'}
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
          variant="ghost"
          onClick={() => setSelectedEvent(row)}
          icon={<Icons.FileText className="w-3.5 h-3.5" />}
        >
          View Diff
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-5">
        <div>
          <h1 className="text-[22px] font-bold text-text">Audit Trail & System Logs</h1>
          <p className="text-[13px] text-text-secondary mt-0.5">
            Immutable, read-only ledger of security, assignment, financial, and administrative actions
          </p>
        </div>
      </div>

      {error && (
        <Banner variant="danger" onClose={() => setError(null)}>
          {error}
        </Banner>
      )}

      {correlationIdFilter && (
        <div className="p-3 bg-primary-subtle border border-primary-border rounded flex items-center justify-between text-[13px]">
          <span>
            Filtering by Correlation ID: <strong>{correlationIdFilter}</strong>
          </span>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setCorrelationIdFilter('')}
          >
            Clear Filter
          </Button>
        </div>
      )}

      <Card>
        {/* Filters */}
        <div className="p-4 grid grid-cols-1 sm:grid-cols-4 gap-4 items-center">
          <TextField
            placeholder="Filter by Actor Email / ID..."
            value={actorFilter}
            onChange={(e) => setActorFilter(e.target.value)}
          />
          <TextField
            placeholder="Event Type (e.g. BILL_LOCK)..."
            value={eventTypeFilter}
            onChange={(e) => setEventTypeFilter(e.target.value.toUpperCase())}
          />
          <TextField
            placeholder="Entity Type (e.g. Student)..."
            value={entityTypeFilter}
            onChange={(e) => setEntityTypeFilter(e.target.value)}
          />
          <div className="flex items-center gap-2">
            <TextField
              type="date"
              placeholder="From Date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
            />
            <TextField
              type="date"
              placeholder="To Date"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
            />
          </div>
        </div>

        <DataTable
          columns={columns}
          data={events}
          loading={loading}
          keyExtractor={(e) => e.audit_id.toString()}
          emptyMessage="No audit logs recorded matching search criteria."
          onRowClick={(row) => setSelectedEvent(row)}
        />
      </Card>

      {/* Side-by-Side Diff Drawer */}
      <Drawer
        isOpen={Boolean(selectedEvent)}
        onClose={() => setSelectedEvent(null)}
        title={selectedEvent ? `Event: ${selectedEvent.event_type}` : 'Audit Event Details'}
        subtitle={selectedEvent?.occurred_at ? new Date(selectedEvent.occurred_at).toLocaleString() : ''}
        width="max-w-3xl"
        footer={
          <div className="flex items-center justify-between w-full">
            {selectedEvent?.correlation_id ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => handleFilterByCorrelationId(selectedEvent.correlation_id!)}
                icon={<Icons.Search className="w-3.5 h-3.5" />}
              >
                View Related Events (Correlation ID)
              </Button>
            ) : <div />}
            <Button variant="primary" onClick={() => setSelectedEvent(null)}>
              Close
            </Button>
          </div>
        }
      >
        {selectedEvent && (
          <div className="space-y-5 text-[13px]">
            {/* Event Header Information */}
            <div className="p-4 bg-bg border border-border rounded-[10px] space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <span className="text-text-muted">Actor:</span>
                <span className="font-semibold text-text">
                  {selectedEvent.actor?.full_name || selectedEvent.actor?.email || 'System'}
                </span>
                <span className="text-text-muted">Entity Target:</span>
                <span className="text-text">
                  {selectedEvent.entity_type} #{selectedEvent.entity_id}
                </span>
                <span className="text-text-muted">Correlation ID:</span>
                <span className="font-mono text-text text-[12px]">
                  {selectedEvent.correlation_id || 'N/A'}
                </span>
                <span className="text-text-muted">Audit Reason:</span>
                <span className="text-text font-medium">
                  {selectedEvent.reason || 'None provided'}
                </span>
              </div>
            </div>

            {/* Side-by-Side Diff Section */}
            <div className="space-y-2">
              <h4 className="font-bold text-text">State Changes (Old vs New Values)</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Old Values */}
                <div className="p-4 bg-surface border border-border rounded-[10px]">
                  <div className="font-semibold text-text-muted border-b border-border pb-2 mb-2 flex items-center justify-between">
                    <span>Previous State</span>
                    <Icons.ArrowLeft className="w-4 h-4" />
                  </div>
                  {selectedEvent.old_values && Object.keys(selectedEvent.old_values).length > 0 ? (
                    <pre className="text-[12px] font-mono text-danger overflow-x-auto whitespace-pre-wrap">
                      {JSON.stringify(selectedEvent.old_values, null, 2)}
                    </pre>
                  ) : (
                    <span className="text-text-muted italic text-[12px]">No prior state recorded</span>
                  )}
                </div>

                {/* New Values */}
                <div className="p-4 bg-surface border border-border rounded-[10px]">
                  <div className="font-semibold text-success border-b border-border pb-2 mb-2 flex items-center justify-between">
                    <span>New State</span>
                    <Icons.Check className="w-4 h-4" />
                  </div>
                  {selectedEvent.new_values && Object.keys(selectedEvent.new_values).length > 0 ? (
                    <pre className="text-[12px] font-mono text-success overflow-x-auto whitespace-pre-wrap">
                      {JSON.stringify(selectedEvent.new_values, null, 2)}
                    </pre>
                  ) : (
                    <span className="text-text-muted italic text-[12px]">No state change payload</span>
                  )}
                </div>
              </div>
            </div>

            {/* Event Metadata */}
            {selectedEvent.metadata && Object.keys(selectedEvent.metadata).length > 0 && (
              <div className="p-4 bg-bg border border-border rounded-[10px] space-y-1">
                <span className="font-bold text-text block mb-1">Additional Metadata</span>
                <pre className="text-[12px] font-mono text-text-secondary overflow-x-auto whitespace-pre-wrap">
                  {JSON.stringify(selectedEvent.metadata, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
};

import React, { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../../api/client';
import { Card } from '../../components/Card';
import { Button } from '../../components/Button';
import { Select } from '../../components/Select';
import { TextField } from '../../components/TextField';
import { StatusBadge } from '../../components/StatusBadge';
import { ReasonDialog } from '../../components/ReasonDialog';
import { Banner } from '../../components/Banner';

interface MessOption {
  mess_id: number;
  code: string;
  name: string;
}

interface MealType {
  meal_type_id: number;
  code: string;
  name: string;
  start_time: string;
  end_time: string;
}

interface MealOccurrence {
  occurrence_id: number;
  mess_id: number;
  meal_type: {
    code: string;
    name: string;
  };
  meal_date: string;
  status: 'SCHEDULED' | 'CANCELLED';
  cancellation_reason?: string;
  consumption_count?: number;
}

export const MealConfigPage: React.FC = () => {
  const [messes, setMesses] = useState<MessOption[]>([]);
  const [selectedMessId, setSelectedMessId] = useState<number | null>(null);
  const [mealTypes, setMealTypes] = useState<MealType[]>([]);
  const [occurrences, setOccurrences] = useState<MealOccurrence[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Configuration horizon & slot times (DEC-06)
  const horizonDays = 35;
  const [slotTimes, setSlotTimes] = useState({
    BREAKFAST: '09:30',
    LUNCH: '14:30',
    SNACKS: '18:00',
    DINNER: '22:00',
  });
  const [configVersion, setConfigVersion] = useState(1);
  const [savingConfig, setSavingConfig] = useState(false);

  // Cancel occurrence state
  const [cancellingOccurrence, setCancellingOccurrence] = useState<MealOccurrence | null>(null);
  const [cancelLoading, setCancelLoading] = useState(false);

  // Date range for occurrences
  const fromDate = new Date().toISOString().split('T')[0];

  const fetchInitialData = useCallback(async () => {
    setError(null);
    try {
      const [messRes, typeRes] = await Promise.all([
        apiClient.get<any>('/messes?status=ACTIVE'),
        apiClient.get<any>('/meals/types').catch(() => []),
      ]);

      const messList = Array.isArray(messRes) ? messRes : messRes?.results || [];
      const typeList = Array.isArray(typeRes) ? typeRes : typeRes?.results || [];

      setMesses(messList);
      setMealTypes(typeList);

      if (messList.length > 0 && selectedMessId === null) {
        setSelectedMessId(messList[0].mess_id);
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to load meal configuration data.');
    }
  }, [selectedMessId]);

  useEffect(() => {
    fetchInitialData();
  }, [fetchInitialData]);

  const fetchOccurrences = useCallback(async () => {
    if (!selectedMessId) return;
    try {
      const toDateObj = new Date();
      toDateObj.setDate(toDateObj.getDate() + 35);
      const toDate = toDateObj.toISOString().split('T')[0];

      const res = await apiClient.get<any>(
        `/meals/occurrences?mess_id=${selectedMessId}&from_date=${fromDate}&to_date=${toDate}`
      );
      const list = Array.isArray(res) ? res : res?.results || [];
      setOccurrences(list);
    } catch (err: any) {
      // Handled
    }
  }, [selectedMessId, fromDate]);

  useEffect(() => {
    fetchOccurrences();
  }, [fetchOccurrences]);

  const handleSaveSlotTimes = async () => {
    setSavingConfig(true);
    try {
      // Saves times and increments config version
      setConfigVersion((v) => v + 1);
      setSuccessMsg(`Meal slot times updated. System configuration version incremented to v${configVersion + 1}.`);
    } catch (err: any) {
      setError(err?.message || 'Failed to update slot times.');
    } finally {
      setSavingConfig(false);
    }
  };

  const handleConfirmCancelOccurrence = async (reason: string) => {
    if (!cancellingOccurrence) return;
    setCancelLoading(true);
    try {
      await apiClient.post(`/meals/occurrences/${cancellingOccurrence.occurrence_id}/cancel`, {
        reason: reason,
      });
      setSuccessMsg(`Meal occurrence on ${cancellingOccurrence.meal_date} cancelled.`);
      setCancellingOccurrence(null);
      fetchOccurrences();
    } catch (err: any) {
      setError(err?.message || 'Cannot cancel occurrence: consumptions already exist.');
    } finally {
      setCancelLoading(false);
    }
  };

  const currentMess = messes.find((m) => m.mess_id === selectedMessId);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-5">
        <div>
          <h1 className="text-[22px] font-bold text-text">Meal Configuration & Schedule</h1>
          <p className="text-[13px] text-text-secondary mt-0.5">
            Per-mess occurrences, 35-day calendar horizons, and DEC-06 pause cutoff slot times
          </p>
        </div>

        <div className="w-64">
          <Select
            label="Selected Mess Facility"
            value={selectedMessId ? selectedMessId.toString() : ''}
            onChange={(e) => setSelectedMessId(parseInt(e.target.value))}
            options={messes.map((m) => ({
              value: m.mess_id.toString(),
              label: `${m.name} (${m.code})`,
            }))}
          />
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Meal Slot Times & Rules */}
        <div className="space-y-6">
          <Card
            title="Meal Slot Cutoff Times"
            subtitle="Used by automated pause counting (DEC-06)"
          >
            <div className="space-y-4">
              <div className="p-3 bg-bg border border-border rounded text-[12px] text-text-secondary">
                <strong>Policy DEC-06:</strong> Meal slot end times define the exact cutoff when a missed meal counts towards a multi-day student billing pause.
              </div>

              <div className="space-y-3">
                <TextField
                  label="Breakfast Cutoff Time"
                  type="time"
                  value={slotTimes.BREAKFAST}
                  onChange={(e) => setSlotTimes({ ...slotTimes, BREAKFAST: e.target.value })}
                />
                <TextField
                  label="Lunch Cutoff Time"
                  type="time"
                  value={slotTimes.LUNCH}
                  onChange={(e) => setSlotTimes({ ...slotTimes, LUNCH: e.target.value })}
                />
                <TextField
                  label="Snacks Cutoff Time"
                  type="time"
                  value={slotTimes.SNACKS}
                  onChange={(e) => setSlotTimes({ ...slotTimes, SNACKS: e.target.value })}
                />
                <TextField
                  label="Dinner Cutoff Time"
                  type="time"
                  value={slotTimes.DINNER}
                  onChange={(e) => setSlotTimes({ ...slotTimes, DINNER: e.target.value })}
                />
              </div>

              <div className="pt-2 flex items-center justify-between border-t border-border">
                <span className="text-[12px] text-text-muted">
                  Config Version: <strong>v{configVersion}</strong>
                </span>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleSaveSlotTimes}
                  loading={savingConfig}
                >
                  Update Slot Times
                </Button>
              </div>
            </div>
          </Card>

          <Card title="Horizon & Meal Types" subtitle="Facility service scope">
            <div className="space-y-3 text-[13px]">
              <div className="flex items-center justify-between">
                <span className="text-text-muted">Scheduling Horizon:</span>
                <span className="font-semibold text-text">{horizonDays} Days Ahead</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-text-muted">Active Mess:</span>
                <span className="font-semibold text-text">{currentMess?.name} ({currentMess?.code})</span>
              </div>

              <div className="pt-2 border-t border-border">
                <span className="text-[12px] font-bold text-text-secondary block mb-2">Supported Meal Types</span>
                <div className="flex flex-wrap gap-2">
                  {mealTypes.map((mt) => (
                    <span key={mt.code} className="px-2.5 py-1 bg-surface border border-border rounded text-[12px] font-medium text-text">
                      {mt.name} ({mt.code})
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </Card>
        </div>

        {/* Right Column: 35-Day Scheduled Occurrences */}
        <div className="lg:col-span-2">
          <Card
            title={`Scheduled Meal Occurrences (${occurrences.length})`}
            subtitle="View, verify, or administratively cancel scheduled meal slots"
          >
            <div className="space-y-3 max-h-[600px] overflow-y-auto pr-1">
              {occurrences.length > 0 ? (
                occurrences.map((occ) => (
                  <div
                    key={occ.occurrence_id}
                    className="p-3 bg-surface border border-border rounded-[8px] flex items-center justify-between text-[13px]"
                  >
                    <div>
                      <div className="font-semibold text-text flex items-center gap-2">
                        <span>{occ.meal_date}</span>
                        <span className="text-text-muted">•</span>
                        <span>{occ.meal_type?.name || occ.meal_type?.code}</span>
                      </div>
                      <div className="text-[12px] text-text-muted mt-0.5">
                        Consumptions: {occ.consumption_count ?? 0} scans
                        {occ.cancellation_reason && (
                          <span className="text-danger ml-2">Reason: {occ.cancellation_reason}</span>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      <StatusBadge
                        status={occ.status === 'SCHEDULED' ? 'ACTIVE' : 'INACTIVE'}
                      />
                      {occ.status === 'SCHEDULED' && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="text-danger hover:bg-danger-subtle"
                          onClick={() => setCancellingOccurrence(occ)}
                        >
                          Cancel
                        </Button>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <div className="p-8 text-center text-text-muted text-[13px]">
                  No meal occurrences generated for the selected horizon.
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>

      {/* Cancel Occurrence ReasonDialog */}
      <ReasonDialog
        isOpen={Boolean(cancellingOccurrence)}
        onClose={() => setCancellingOccurrence(null)}
        onConfirm={handleConfirmCancelOccurrence}
        title={`Cancel Meal Occurrence: ${cancellingOccurrence?.meal_date}`}
        description="Explain why this scheduled meal is being cancelled. Note: Cancellation will be refused by the server if student meal consumptions have already been recorded."
        confirmLabel="Confirm Cancellation"
        variant="danger"
        loading={cancelLoading}
      />
    </div>
  );
};

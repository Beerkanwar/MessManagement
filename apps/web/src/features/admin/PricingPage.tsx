import React, { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../../api/client';
import { Card } from '../../components/Card';
import { DataTable, Column } from '../../components/DataTable';
import { Button } from '../../components/Button';
import { Drawer } from '../../components/Drawer';
import { TextField } from '../../components/TextField';
import { Select } from '../../components/Select';
import { Tabs } from '../../components/Tabs';
import { Banner } from '../../components/Banner';
import { Icons } from '../../components/Icons';

interface MessOption {
  mess_id: number;
  code: string;
  name: string;
}

interface MealRate {
  meal_rate_id: number;
  rate: string;
  effective_from: string;
  effective_to?: string;
  version?: number;
  created_at?: string;
}

interface ExtraItem {
  extra_item_id: number;
  code: string;
  name: string;
  hostel_id: number;
  hostel_code?: string;
  hostel_name?: string;
  current_price?: string;
  status: 'ACTIVE' | 'INACTIVE';
}

export const PricingPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'rates' | 'extras'>('rates');
  const [messes, setMesses] = useState<MessOption[]>([]);
  const [selectedMessId, setSelectedMessId] = useState<number | null>(null);
  const [mealRates, setMealRates] = useState<MealRate[]>([]);
  const [extraItems, setExtraItems] = useState<ExtraItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Add Rate Form state
  const [rateDrawerOpen, setRateDrawerOpen] = useState(false);
  const [newRate, setNewRate] = useState('');
  const [newRateEffectiveFrom, setNewRateEffectiveFrom] = useState('');
  const [newRateReason, setNewRateReason] = useState('');
  const [rateSubmitting, setRateSubmitting] = useState(false);

  // Add Extra Price Form state
  const [extraPriceDrawerOpen, setExtraPriceDrawerOpen] = useState(false);
  const [selectedExtraItem, setSelectedExtraItem] = useState<ExtraItem | null>(null);
  const [newExtraPrice, setNewExtraPrice] = useState('');
  const [newExtraEffectiveFrom, setNewExtraEffectiveFrom] = useState('');
  const [newExtraReason, setNewExtraReason] = useState('');
  const [extraPriceSubmitting, setExtraPriceSubmitting] = useState(false);

  // Today ISO date
  const today = new Date().toISOString().split('T')[0];

  const fetchInitialData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [mRes, extrasRes] = await Promise.all([
        apiClient.get<any>('/messes?status=ACTIVE'),
        apiClient.get<any>('/extras/items').catch(() => ({ results: [] })),
      ]);

      const mList = Array.isArray(mRes) ? mRes : mRes?.results || [];
      const eList = Array.isArray(extrasRes) ? extrasRes : extrasRes?.results || [];

      setMesses(mList);
      setExtraItems(eList);

      if (mList.length > 0 && selectedMessId === null) {
        setSelectedMessId(mList[0].mess_id);
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to load pricing data.');
    } finally {
      setLoading(false);
    }
  }, [selectedMessId]);

  useEffect(() => {
    fetchInitialData();
  }, [fetchInitialData]);

  const fetchRatesForMess = useCallback(async (messId: number) => {
    try {
      const res = await apiClient.get<any>(`/messes/${messId}/meal-rates`);
      const list = Array.isArray(res) ? res : res?.results || [];
      setMealRates(list);
    } catch {
      setMealRates([]);
    }
  }, []);

  useEffect(() => {
    if (selectedMessId) {
      fetchRatesForMess(selectedMessId);
    }
  }, [selectedMessId, fetchRatesForMess]);

  const handleAddMealRate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedMessId || !newRate || !newRateEffectiveFrom) return;
    setRateSubmitting(true);
    try {
      await apiClient.post(`/messes/${selectedMessId}/meal-rates`, {
        rate: parseFloat(newRate),
        effective_from: newRateEffectiveFrom,
        reason: newRateReason,
      });
      setSuccessMsg(`New meal rate of ₹${newRate} effective from ${newRateEffectiveFrom} saved.`);
      setRateDrawerOpen(false);
      fetchRatesForMess(selectedMessId);
    } catch (err: any) {
      setError(err?.message || 'Failed to add meal rate.');
    } finally {
      setRateSubmitting(false);
    }
  };

  const handleAddExtraPrice = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedExtraItem || !newExtraPrice || !newExtraEffectiveFrom) return;
    setExtraPriceSubmitting(true);
    try {
      await apiClient.post(`/extras/items/${selectedExtraItem.extra_item_id}/prices`, {
        unit_price: parseFloat(newExtraPrice),
        effective_from: newExtraEffectiveFrom,
        reason: newExtraReason,
      });
      setSuccessMsg(
        `New price ₹${newExtraPrice} for "${selectedExtraItem.name}" effective from ${newExtraEffectiveFrom} saved.`
      );
      setExtraPriceDrawerOpen(false);
      // Reload extras
      const extrasRes = await apiClient.get<any>('/extras/items');
      setExtraItems(Array.isArray(extrasRes) ? extrasRes : extrasRes?.results || []);
    } catch (err: any) {
      setError(err?.message || 'Failed to add extra price.');
    } finally {
      setExtraPriceSubmitting(false);
    }
  };

  const rateColumns: Column<MealRate>[] = [
    {
      key: 'rate',
      header: 'Common Daily Rate',
      render: (row) => <span className="font-bold text-text">₹{parseFloat(row.rate).toFixed(2)}</span>,
    },
    {
      key: 'effective_from',
      header: 'Effective From',
      render: (row) => <span>{row.effective_from}</span>,
    },
    {
      key: 'effective_to',
      header: 'Effective To',
      render: (row) => (
        <span>{row.effective_to ? row.effective_to : <strong className="text-success">Current Rate</strong>}</span>
      ),
    },
    {
      key: 'version',
      header: 'Version',
      render: (row) => <span className="font-mono text-[12px]">v{row.version || 1}</span>,
    },
  ];

  const extraColumns: Column<ExtraItem>[] = [
    {
      key: 'code',
      header: 'Item Code',
      render: (row) => <span className="font-mono font-bold text-text">{row.code}</span>,
    },
    {
      key: 'name',
      header: 'Extra Item Name',
      render: (row) => <span className="font-medium text-text">{row.name}</span>,
    },
    {
      key: 'hostel',
      header: 'Hostel Facility',
      render: (row) => <span>{row.hostel_name || row.hostel_code || 'All Hostels'}</span>,
    },
    {
      key: 'current_price',
      header: 'Current Price',
      render: (row) => (
        <span className="font-bold text-text">
          {row.current_price ? `₹${parseFloat(row.current_price).toFixed(2)}` : '—'}
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
          onClick={() => {
            setSelectedExtraItem(row);
            setNewExtraPrice('');
            setNewExtraEffectiveFrom(today);
            setNewExtraReason('');
            setExtraPriceDrawerOpen(true);
          }}
          icon={<Icons.Plus className="w-3.5 h-3.5" />}
        >
          Add Future Price
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-5">
        <div>
          <h1 className="text-[22px] font-bold text-text">Pricing & Rates Master</h1>
          <p className="text-[13px] text-text-secondary mt-0.5">
            Effective-dated daily common meal rates and hostel extra food pricing schedules
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

      {/* Mandatory pricing rule banner */}
      <div className="p-3 bg-bg border border-border rounded-[10px] text-[13px] text-text-secondary flex items-start gap-2">
        <Icons.Info className="w-4 h-4 text-primary flex-shrink-0 mt-0.5" />
        <div>
          <strong>Pricing Immutable Rule:</strong> Past prices cannot be changed; earlier transactions always keep their recorded price. The common rate applies to Breakfast, Lunch and Dinner. New rates take effect today or on a future date.
        </div>
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={(k) => setActiveTab(k as 'rates' | 'extras')}
        items={[
          { key: 'rates', label: 'Common Meal Rates' },
          { key: 'extras', label: 'Hostel Extra Items' },
        ]}
      />

      {/* TAB 1: Meal Rates */}
      {activeTab === 'rates' && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div className="w-64">
              <Select
                label="Filter by Mess Facility"
                value={selectedMessId ? selectedMessId.toString() : ''}
                onChange={(e) => setSelectedMessId(parseInt(e.target.value))}
                options={messes.map((m) => ({
                  value: m.mess_id.toString(),
                  label: `${m.name} (${m.code})`,
                }))}
              />
            </div>

            <Button
              variant="primary"
              onClick={() => {
                setNewRate('');
                setNewRateEffectiveFrom(today);
                setNewRateReason('');
                setRateDrawerOpen(true);
              }}
              icon={<Icons.Plus className="w-4 h-4" />}
            >
              Add New Rate
            </Button>
          </div>

          <Card title="Rate Version History">
            <DataTable
              columns={rateColumns}
              data={mealRates}
              loading={loading}
              keyExtractor={(r: MealRate) => (r?.meal_rate_id != null ? String(r.meal_rate_id) : 'rate')}
              emptyMessage="No meal rates recorded for this mess yet."
            />
          </Card>
        </div>
      )}

      {/* TAB 2: Extra Items */}
      {activeTab === 'extras' && (
        <div className="space-y-4">
          <Card title="Hostel Extras Pricing Schedule">
            <DataTable
              columns={extraColumns}
              data={extraItems}
              loading={loading}
              keyExtractor={(e: ExtraItem) => (e?.extra_item_id != null ? String(e.extra_item_id) : 'extra')}
              emptyMessage="No extra food items registered yet."
            />
          </Card>
        </div>
      )}

      {/* Add Rate Drawer */}
      <Drawer
        isOpen={rateDrawerOpen}
        onClose={() => setRateDrawerOpen(false)}
        title="Add Common Meal Rate"
        subtitle="Rule: Past prices cannot be changed; earlier transactions keep their price. Common rate applies to Breakfast, Lunch and Dinner."
        width="max-w-md"
        footer={
          <div className="flex items-center justify-end gap-3 w-full">
            <Button variant="secondary" onClick={() => setRateDrawerOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={handleAddMealRate} loading={rateSubmitting}>
              Save Rate
            </Button>
          </div>
        }
      >
        <form onSubmit={handleAddMealRate} className="space-y-4">
          <div className="p-3 bg-bg border border-border rounded text-[12px] text-text-secondary">
            Common rate applies universally across Breakfast, Lunch, and Dinner.
          </div>

          <TextField
            label="Daily Meal Rate (₹)"
            type="number"
            step="0.01"
            min="0"
            required
            value={newRate}
            onChange={(e) => setNewRate(e.target.value)}
            placeholder="e.g. 150.00"
          />

          <TextField
            label="Effective From Date"
            type="date"
            min={today}
            required
            value={newRateEffectiveFrom}
            onChange={(e) => setNewRateEffectiveFrom(e.target.value)}
            helperText="Must be today or a future date. Historical dates are rejected."
          />

          <TextField
            label="Administrative Reason"
            placeholder="e.g. Semester rate revision / Commodity adjustment"
            value={newRateReason}
            onChange={(e) => setNewRateReason(e.target.value)}
          />
        </form>
      </Drawer>

      {/* Add Extra Price Drawer */}
      <Drawer
        isOpen={extraPriceDrawerOpen}
        onClose={() => setExtraPriceDrawerOpen(false)}
        title={`Set Price: ${selectedExtraItem?.name}`}
        subtitle="Rule: Past prices cannot be changed; earlier transactions keep their price."
        width="max-w-md"
        footer={
          <div className="flex items-center justify-end gap-3 w-full">
            <Button variant="secondary" onClick={() => setExtraPriceDrawerOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={handleAddExtraPrice} loading={extraPriceSubmitting}>
              Save Price
            </Button>
          </div>
        }
      >
        <form onSubmit={handleAddExtraPrice} className="space-y-4">
          <TextField
            label="Unit Price (₹)"
            type="number"
            step="0.01"
            min="0"
            required
            value={newExtraPrice}
            onChange={(e) => setNewExtraPrice(e.target.value)}
            placeholder="e.g. 40.00"
          />

          <TextField
            label="Effective From Date"
            type="date"
            min={today}
            required
            value={newExtraEffectiveFrom}
            onChange={(e) => setNewExtraEffectiveFrom(e.target.value)}
            helperText="Must be today or a future date."
          />

          <TextField
            label="Administrative Reason"
            placeholder="e.g. Vendor price adjustment"
            value={newExtraReason}
            onChange={(e) => setNewExtraReason(e.target.value)}
          />
        </form>
      </Drawer>
    </div>
  );
};

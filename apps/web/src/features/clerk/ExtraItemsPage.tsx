import React, { useState, useEffect, useCallback } from 'react';
import { Card } from '../../components/Card';
import { Button } from '../../components/Button';
import { TextField } from '../../components/TextField';
import { DatePicker } from '../../components/DatePicker';
import { Drawer } from '../../components/Drawer';
import { MoneyText } from '../../components/MoneyText';
import { DateText } from '../../components/DateText';
import { Skeleton } from '../../components/Skeleton';
import { ErrorState } from '../../components/ErrorState';
import { EmptyState } from '../../components/EmptyState';
import { Icons } from '../../components/Icons';
import { apiClient } from '../../api/client';
import { useAuth } from '../../state/auth';

interface PriceRow {
  price_id: number;
  price: number;
  effective_from: string;
  effective_to?: string | null;
  created_by_email?: string;
  created_at?: string;
}

interface ExtraItem {
  item_id: number;
  name: string;
  is_active: boolean;
  current_price?: number;
  next_price_change?: string | null;
  updated_at?: string;
  prices?: PriceRow[];
}

export const ExtraItemsPage: React.FC = () => {
  const { assignment } = useAuth();
  const [items, setItems] = useState<ExtraItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ code: string; message: string; traceId?: string } | null>(null);

  // New Item Modal
  const [isNewItemOpen, setIsNewItemOpen] = useState(false);
  const [newItemName, setNewItemName] = useState('');
  const [newItemPrice, setNewItemPrice] = useState('');
  const [newSubmitting, setNewSubmitting] = useState(false);

  // Detail & Price Drawer
  const [selectedItem, setSelectedItem] = useState<ExtraItem | null>(null);
  const [itemPrices, setItemPrices] = useState<PriceRow[]>([]);
  const [loadingPrices, setLoadingPrices] = useState(false);

  // Add Price Form
  const [newPriceAmount, setNewPriceAmount] = useState('');
  const [newPriceEffectiveFrom, setNewPriceEffectiveFrom] = useState('');
  const [priceSubmitting, setPriceSubmitting] = useState(false);
  const [priceError, setPriceError] = useState<string | null>(null);

  const scopeLabel = assignment?.hostel_name || 'Assigned Hostel';

  const fetchItems = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.get<any>('/extras/items');
      const list = data?.results || (Array.isArray(data) ? data : []);
      const formatted: ExtraItem[] = list.map((item: any) => ({
        item_id: item.item_id || item.id,
        name: item.name,
        is_active: item.is_active ?? true,
        current_price: item.current_price ?? (item.prices?.[0]?.price || 0),
        next_price_change: item.next_price_change || null,
        updated_at: item.updated_at || item.created_at,
        prices: item.prices || [],
      }));
      setItems(formatted);
    } catch (err: any) {
      setError({
        code: err.code || 'EXTRAS_FETCH_FAILED',
        message: err.message || 'Unable to load extra items.',
        traceId: err.traceId,
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  const loadItemPrices = async (itemId: number) => {
    setLoadingPrices(true);
    try {
      const data = await apiClient.get<any>(`/extras/items/${itemId}/prices`);
      const prices = data?.results || (Array.isArray(data) ? data : []);
      setItemPrices(prices);
    } catch {
      setItemPrices([]);
    } finally {
      setLoadingPrices(false);
    }
  };

  const handleSelectItem = (item: ExtraItem) => {
    setSelectedItem(item);
    setNewPriceAmount('');
    const today = new Date().toISOString().split('T')[0];
    setNewPriceEffectiveFrom(today);
    setPriceError(null);
    loadItemPrices(item.item_id);
  };

  const handleCreateItem = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newItemName.trim()) return;

    // Check unique case-insensitive per hostel
    if (items.some((i) => i.name.toLowerCase() === newItemName.trim().toLowerCase())) {
      alert(`An extra item named "${newItemName.trim()}" already exists in this hostel.`);
      return;
    }

    setNewSubmitting(true);
    try {
      const created = await apiClient.post<any>('/extras/items', {
        name: newItemName.trim(),
        hostel_id: assignment?.hostel_id,
      });
      const itemId = created.item_id || created.id;

      // If price was also entered, create initial price
      if (newItemPrice && Number(newItemPrice) > 0) {
        const today = new Date().toISOString().split('T')[0];
        await apiClient.post(`/extras/items/${itemId}/prices`, {
          price: Number(newItemPrice),
          effective_from: today,
        });
      }

      setIsNewItemOpen(false);
      setNewItemName('');
      setNewItemPrice('');
      fetchItems();
    } catch (err: any) {
      alert(err.message || 'Failed to create item');
    } finally {
      setNewSubmitting(false);
    }
  };

  const handleToggleActive = async (item: ExtraItem) => {
    try {
      if (item.is_active) {
        await apiClient.post(`/extras/items/${item.item_id}/deactivate`, {});
      } else {
        await apiClient.patch(`/extras/items/${item.item_id}`, { is_active: true });
      }
      setItems((prev) =>
        prev.map((i) => (i.item_id === item.item_id ? { ...i, is_active: !i.is_active } : i))
      );
      if (selectedItem?.item_id === item.item_id) {
        setSelectedItem((prev) => (prev ? { ...prev, is_active: !prev.is_active } : null));
      }
    } catch (err: any) {
      alert(err.message || 'Failed to update item status');
    }
  };

  const handleAddPrice = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedItem) return;
    setPriceError(null);

    const price = Number(newPriceAmount);
    if (!price || price <= 0) {
      setPriceError('Please enter a valid price amount greater than 0.');
      return;
    }

    // Verify effective_from is today or later
    const today = new Date().toISOString().split('T')[0];
    if (newPriceEffectiveFrom < today) {
      setPriceError('Past prices cannot be changed; new prices must be effective from today or a future date.');
      return;
    }

    setPriceSubmitting(true);
    try {
      await apiClient.post(`/extras/items/${selectedItem.item_id}/prices`, {
        price,
        effective_from: newPriceEffectiveFrom,
      });
      setNewPriceAmount('');
      loadItemPrices(selectedItem.item_id);
      fetchItems();
    } catch (err: any) {
      setPriceError(err.message || 'Failed to save price version.');
    } finally {
      setPriceSubmitting(false);
    }
  };

  return (
    <div className="space-y-6 select-none">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-5">
        <div>
          <div className="flex items-center gap-2.5">
            <h2 className="text-[22px] font-bold text-text">Extra Items & Prices</h2>
            <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-primary-subtle text-primary border border-primary-border">
              Scope: {scopeLabel}
            </span>
          </div>
          <p className="text-[13px] text-text-secondary mt-0.5">
            Manage hostel canteen items and effective-dated unit prices.
          </p>
        </div>

        <Button
          variant="primary"
          onClick={() => setIsNewItemOpen(true)}
          icon={<Icons.Plus className="w-4 h-4" />}
        >
          New Extra Item
        </Button>
      </div>

      {/* Immutable Price Hint */}
      <div className="p-3 bg-bg border border-border rounded-[8px] flex items-center gap-2.5 text-[13px] text-text-secondary">
        <Icons.Info className="w-4 h-4 shrink-0 text-text-muted" />
        <span>
          Past prices cannot be changed; earlier transactions keep their price snapshots. New prices take effect today or on a scheduled future date.
        </span>
      </div>

      {/* Error state */}
      {error && (
        <ErrorState
          errorCode={error.code}
          message={error.message}
          traceId={error.traceId}
          onRetry={fetchItems}
        />
      )}

      {/* Loading */}
      {loading && !error && (
        <div className="space-y-3 p-6 bg-surface border border-border rounded-[10px]">
          <Skeleton height={32} width="40%" />
          <Skeleton height={24} />
          <Skeleton height={24} />
        </div>
      )}

      {/* Empty State */}
      {!loading && !error && items.length === 0 && (
        <EmptyState
          title="No Extra Items Configured"
          description="Create 'Evening Snacks' or other hostel-specific extras to enable additional student purchases."
          action={{
            label: 'Create Evening Snacks',
            onClick: () => {
              setNewItemName('Evening Snacks');
              setIsNewItemOpen(true);
            },
          }}
          icon={<Icons.Plus className="w-6 h-6 stroke-[1.5]" />}
        />
      )}

      {/* Items Table */}
      {!loading && !error && items.length > 0 && (
        <div className="border border-border rounded-[10px] bg-surface overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-[14px]">
              <thead className="bg-bg border-b border-border-strong text-[13px] font-semibold text-text">
                <tr>
                  <th className="px-4 py-3">Item Name</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3 text-right">Current Price</th>
                  <th className="px-4 py-3">Next Scheduled Change</th>
                  <th className="px-4 py-3">Last Updated</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {items.map((item) => (
                  <tr
                    key={item.item_id}
                    onClick={() => handleSelectItem(item)}
                    className="hover:bg-bg/50 cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3 font-semibold text-text">
                      {item.name}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold border ${
                          item.is_active
                            ? 'bg-success-subtle text-success border-[#BBF7D0]'
                            : 'bg-bg text-text-muted border-border'
                        }`}
                      >
                        {item.is_active ? 'ACTIVE' : 'INACTIVE'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      <MoneyText amountInRupees={item.current_price || 0} />
                    </td>
                    <td className="px-4 py-3 text-text-muted text-[13px]">
                      {item.next_price_change ? (
                        <DateText date={item.next_price_change} />
                      ) : (
                        'None scheduled'
                      )}
                    </td>
                    <td className="px-4 py-3 text-text-muted text-[13px]">
                      {item.updated_at ? <DateText date={item.updated_at} /> : '-'}
                    </td>
                    <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleSelectItem(item)}
                      >
                        Manage Prices
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Create New Item Dialog */}
      {isNewItemOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="fixed inset-0 bg-[#0F172A]/40 backdrop-blur-[1px]" onClick={() => setIsNewItemOpen(false)} />
          <form
            onSubmit={handleCreateItem}
            className="relative w-full max-w-md bg-surface border border-border rounded-[16px] shadow-2xl p-6 z-10 space-y-4"
          >
            <h3 className="text-[18px] font-bold text-text">Create Extra Item</h3>
            <p className="text-[13px] text-text-secondary">
              Added to <strong>{scopeLabel}</strong>. Item names are unique per hostel.
            </p>

            <TextField
              label="Item Name"
              required
              placeholder="e.g. Evening Snacks, Boiled Eggs"
              value={newItemName}
              onChange={(e) => setNewItemName(e.target.value)}
            />

            <TextField
              label="Initial Price (₹, optional)"
              type="number"
              step="0.5"
              min="0"
              placeholder="e.g. 25.00"
              value={newItemPrice}
              onChange={(e) => setNewItemPrice(e.target.value)}
              helperText="Takes effect today automatically"
            />

            <div className="flex justify-end gap-3 pt-2">
              <Button variant="secondary" type="button" onClick={() => setIsNewItemOpen(false)}>
                Cancel
              </Button>
              <Button variant="primary" type="submit" loading={newSubmitting}>
                Create Item
              </Button>
            </div>
          </form>
        </div>
      )}

      {/* Item Detail & Price History Drawer */}
      <Drawer
        isOpen={Boolean(selectedItem)}
        onClose={() => setSelectedItem(null)}
        title={selectedItem?.name || 'Extra Item'}
        subtitle={`Item #${selectedItem?.item_id} • ${scopeLabel}`}
        width="max-w-lg"
      >
        {selectedItem && (
          <div className="space-y-6 text-[13px]">
            {/* Status & Deactivate button */}
            <div className="p-4 bg-bg rounded-[8px] border border-border flex items-center justify-between">
              <div>
                <span className="block text-text-muted text-[11px] font-medium uppercase">Current Status</span>
                <span className="text-[14px] font-semibold text-text">
                  {selectedItem.is_active ? 'Active for student orders' : 'Deactivated'}
                </span>
              </div>
              <Button
                variant={selectedItem.is_active ? 'danger' : 'primary'}
                size="sm"
                onClick={() => handleToggleActive(selectedItem)}
              >
                {selectedItem.is_active ? 'Deactivate' : 'Activate'}
              </Button>
            </div>

            {/* Add Price Version Form */}
            <Card title="Add Effective-Dated Price" subtitle="Takes effect today or on a scheduled future date">
              <form onSubmit={handleAddPrice} className="space-y-4">
                {priceError && (
                  <div role="alert" className="p-2.5 bg-danger-subtle text-danger border border-danger/30 rounded text-[12px] font-medium">
                    {priceError}
                  </div>
                )}
                <div className="grid grid-cols-2 gap-3">
                  <TextField
                    label="Price in ₹"
                    type="number"
                    step="0.5"
                    min="1"
                    required
                    placeholder="30.00"
                    value={newPriceAmount}
                    onChange={(e) => setNewPriceAmount(e.target.value)}
                  />
                  <DatePicker
                    label="Effective From"
                    required
                    value={newPriceEffectiveFrom}
                    onChange={(e) => setNewPriceEffectiveFrom(e.target.value)}
                  />
                </div>
                <Button variant="primary" size="sm" type="submit" loading={priceSubmitting} className="w-full justify-center">
                  Set New Price Version
                </Button>
              </form>
            </Card>

            {/* Price History Table */}
            <div>
              <h4 className="font-semibold text-text mb-3">Price Version History</h4>
              {loadingPrices ? (
                <Skeleton height={40} />
              ) : itemPrices.length === 0 ? (
                <div className="p-4 bg-bg rounded text-center text-text-muted">
                  No price history recorded yet.
                </div>
              ) : (
                <div className="border border-border rounded-[8px] overflow-hidden bg-surface">
                  <table className="w-full text-left text-[12px]">
                    <thead className="bg-bg border-b border-border font-semibold text-text">
                      <tr>
                        <th className="px-3 py-2">Price</th>
                        <th className="px-3 py-2">From</th>
                        <th className="px-3 py-2">To</th>
                        <th className="px-3 py-2">Set By</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {itemPrices.map((p, idx) => (
                        <tr key={p.price_id || idx} className="tabular-nums">
                          <td className="px-3 py-2 font-bold text-text">
                            <MoneyText amountInRupees={p.price} />
                          </td>
                          <td className="px-3 py-2">
                            <DateText date={p.effective_from} />
                          </td>
                          <td className="px-3 py-2 text-text-muted">
                            {p.effective_to ? <DateText date={p.effective_to} /> : 'Current'}
                          </td>
                          <td className="px-3 py-2 text-text-secondary truncate max-w-[100px]">
                            {p.created_by_email || 'Staff'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
};
export default ExtraItemsPage;

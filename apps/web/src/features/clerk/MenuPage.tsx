import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Card } from '../../components/Card';
import { Button } from '../../components/Button';
import { StatusBadge } from '../../components/StatusBadge';
import { Skeleton } from '../../components/Skeleton';
import { EmptyState } from '../../components/EmptyState';
import { ErrorState } from '../../components/ErrorState';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Icons } from '../../components/Icons';
import { apiClient } from '../../api/client';
import { useAuth } from '../../state/auth';
import { cn } from '../../lib/utils';

export interface MenuItem {
  menu_item_id?: number;
  food_item_id: number;
  name: string;
  display_order: number;
  notes?: string;
}

export interface MenuMeal {
  menu_meal_id?: number;
  meal_type_id?: number;
  meal_type_code: 'BREAKFAST' | 'LUNCH' | 'EVENING_SNACKS' | 'DINNER';
  meal_type_name: string;
  sequence_no: number;
  status?: string;
  items: MenuItem[];
}

export interface MenuDay {
  date: string; // YYYY-MM-DD
  meals: MenuMeal[];
}

export interface MenuStructure {
  menu_id: number;
  hostel_id: number;
  hostel_code: string;
  hostel_name: string;
  year: number;
  month: number;
  month_label: string;
  status: 'DRAFT' | 'PUBLISHED';
  published_at: string | null;
  published_by_user_id: number | null;
  version: number;
  days: MenuDay[];
}

export interface MenuListItem {
  menu_id: number;
  hostel_id: number;
  hostel_code: string;
  menu_year: number;
  menu_month: number;
  status: 'DRAFT' | 'PUBLISHED';
  published_at: string | null;
  published_by_user_id: number | null;
  version: number;
}

export interface FoodItemMaster {
  food_item_id: number;
  name: string;
  normalized_name?: string;
  description?: string;
  status?: string;
}

const MEAL_TYPES: Array<{ code: 'BREAKFAST' | 'LUNCH' | 'EVENING_SNACKS' | 'DINNER'; name: string }> = [
  { code: 'BREAKFAST', name: 'Breakfast' },
  { code: 'LUNCH', name: 'Lunch' },
  { code: 'EVENING_SNACKS', name: 'Evening Snacks' },
  { code: 'DINNER', name: 'Dinner' },
];

export const MenuPage: React.FC = () => {
  const { assignment } = useAuth();
  const hostelId = assignment?.hostel_id;

  // View mode: 'list' | 'editor'
  const [viewMode, setViewMode] = useState<'list' | 'editor'>('list');
  const [menuList, setMenuList] = useState<MenuListItem[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [listError, setListError] = useState<{ code: string; message: string; traceId?: string } | null>(null);

  // Active Menu in Editor
  const [selectedMenuId, setSelectedMenuId] = useState<number | null>(null);
  const [activeMenu, setActiveMenu] = useState<MenuStructure | null>(null);
  const [loadingMenu, setLoadingMenu] = useState(false);
  const [menuError, setMenuError] = useState<{ code: string; message: string; traceId?: string } | null>(null);

  // Selected Day in Editor (YYYY-MM-DD)
  const [selectedDate, setSelectedDate] = useState<string>('');

  // Food Item Master Catalog for autocomplete
  const [foodCatalog, setFoodCatalog] = useState<FoodItemMaster[]>([]);

  // Modals & Dialogs
  const [showNewMonthModal, setShowNewMonthModal] = useState(false);
  const [newMonthYear, setNewMonthYear] = useState<number>(new Date().getFullYear());
  const [newMonthMonth, setNewMonthMonth] = useState<number>(new Date().getMonth() + 1);
  const [copyPreviousPattern, setCopyPreviousPattern] = useState(false);
  const [creatingMenu, setCreatingMenu] = useState(false);
  const [createMenuError, setCreateMenuError] = useState<string | null>(null);

  // Publish Dialog
  const [showPublishDialog, setShowPublishDialog] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [publishWarnings, setPublishWarnings] = useState<string[]>([]);

  // Optimistic Concurrency Conflict Dialog
  const [conflictDialogOpen, setConflictDialogOpen] = useState(false);

  // Student Preview Modal
  const [showPreviewModal, setShowPreviewModal] = useState(false);

  // Copy Day Modal
  const [showCopyDayModal, setShowCopyDayModal] = useState(false);
  const [copyTargetDates, setCopyTargetDates] = useState<string[]>([]);
  const [copyingDay, setCopyingDay] = useState(false);

  // Create Food Item Inline Dialog
  const [showCreateFoodModal, setShowCreateFoodModal] = useState(false);
  const [newFoodName, setNewFoodName] = useState('');
  const [newFoodDesc, setNewFoodDesc] = useState('');
  const [creatingFood, setCreatingFood] = useState(false);
  const [targetMealForNewFood, setTargetMealForNewFood] = useState<'BREAKFAST' | 'LUNCH' | 'EVENING_SNACKS' | 'DINNER' | null>(null);

  // Active editing state for each meal of the selected day
  const [mealDrafts, setMealDrafts] = useState<Record<string, MenuItem[]>>({});
  const [mealNotes, setMealNotes] = useState<Record<string, Record<number, string>>>({});
  const [mealSaving, setMealSaving] = useState<Record<string, boolean>>({});
  const [mealErrors, setMealErrors] = useState<Record<string, string | null>>({});

  // Fetch Menu List
  const fetchMenuList = useCallback(async () => {
    setLoadingList(true);
    setListError(null);
    try {
      const res = await apiClient.get<any>('/api/v1/menus');
      const items = res.results || res;
      setMenuList(Array.isArray(items) ? items : []);
    } catch (err: any) {
      setListError({
        code: err.code || 'LOAD_FAILED',
        message: err.message || 'Failed to load menu list',
        traceId: err.trace_id,
      });
    } finally {
      setLoadingList(false);
    }
  }, []);

  // Fetch Food Item Catalog
  const fetchFoodCatalog = useCallback(async () => {
    try {
      const res = await apiClient.get<any>('/api/v1/menus/food-items?page_size=200');
      const items = res.results || res;
      setFoodCatalog(Array.isArray(items) ? items : []);
    } catch (err) {
      console.error('Failed to load food catalog', err);
    }
  }, []);

  useEffect(() => {
    fetchMenuList();
    fetchFoodCatalog();
  }, [fetchMenuList, fetchFoodCatalog]);

  // Load Single Menu Details
  const loadMenuDetails = useCallback(async (menuId: number) => {
    setLoadingMenu(true);
    setMenuError(null);
    try {
      const data = await apiClient.get<MenuStructure>(`/api/v1/menus/${menuId}`);
      setActiveMenu(data);
      setSelectedMenuId(menuId);
      if (data.days && data.days.length > 0) {
        setSelectedDate(data.days[0].date);
      }
      setViewMode('editor');
    } catch (err: any) {
      setMenuError({
        code: err.code || 'LOAD_FAILED',
        message: err.message || 'Failed to load menu structure',
        traceId: err.trace_id,
      });
    } finally {
      setLoadingMenu(false);
    }
  }, []);

  // Sync meal draft states when selected date changes or menu updates
  useEffect(() => {
    if (!activeMenu || !selectedDate) return;
    const currentDay = activeMenu.days.find((d) => d.date === selectedDate);
    const drafts: Record<string, MenuItem[]> = {};
    const notesMap: Record<string, Record<number, string>> = {};

    MEAL_TYPES.forEach(({ code }) => {
      const meal = currentDay?.meals.find((m) => m.meal_type_code === code);
      drafts[code] = meal?.items ? [...meal.items] : [];
      notesMap[code] = {};
      meal?.items?.forEach((it) => {
        if (it.notes) {
          notesMap[code][it.food_item_id] = it.notes;
        }
      });
    });

    setMealDrafts(drafts);
    setMealNotes(notesMap);
    setMealErrors({});
  }, [activeMenu, selectedDate]);

  // Calendar Day Coverage calculation
  const getDayStatus = useCallback(
    (day: MenuDay): 'empty' | 'partial' | 'complete' => {
      if (!day.meals || day.meals.length === 0) return 'empty';
      const mealsWithItems = day.meals.filter((m) => m.items && m.items.length > 0).length;
      if (mealsWithItems === 0) return 'empty';
      if (mealsWithItems === 4) return 'complete';
      return 'partial';
    },
    []
  );

  // Days filled count for list view
  const calculateDaysFilled = (days: MenuDay[] = []) => {
    const filled = days.filter((d) => d.meals && d.meals.some((m) => m.items && m.items.length > 0)).length;
    return `${filled} / ${days.length} days`;
  };

  // Create New Month Menu
  const handleCreateMenu = async () => {
    if (!hostelId) {
      setCreateMenuError('No hostel assigned to your clerk account.');
      return;
    }
    setCreatingMenu(true);
    setCreateMenuError(null);
    try {
      const created = await apiClient.post<MenuStructure>('/api/v1/menus', {
        hostel_id: hostelId,
        year: newMonthYear,
        month: newMonthMonth,
      });

      if (copyPreviousPattern && created.menu_id) {
        try {
          await apiClient.post(`/api/v1/menus/${created.menu_id}/copy-previous`, {
            version: created.version,
          });
        } catch (copyErr: any) {
          console.warn('Copy pattern notice:', copyErr.message);
        }
      }

      setShowNewMonthModal(false);
      await fetchMenuList();
      if (created.menu_id) {
        await loadMenuDetails(created.menu_id);
      }
    } catch (err: any) {
      setCreateMenuError(err.message || 'Failed to create menu for the selected month');
    } finally {
      setCreatingMenu(false);
    }
  };

  // Add Food Item to Meal (Prevent Duplicate Food Items [DBDD-AC-30])
  const handleAddFoodToMeal = (mealCode: 'BREAKFAST' | 'LUNCH' | 'EVENING_SNACKS' | 'DINNER', foodItem: FoodItemMaster) => {
    const currentItems = mealDrafts[mealCode] || [];
    const isDuplicate = currentItems.some((it) => it.food_item_id === foodItem.food_item_id);

    if (isDuplicate) {
      setMealErrors((prev) => ({
        ...prev,
        [mealCode]: `"${foodItem.name}" is already in this meal [DBDD-AC-30].`,
      }));
      return;
    }

    setMealErrors((prev) => ({ ...prev, [mealCode]: null }));

    const newItem: MenuItem = {
      food_item_id: foodItem.food_item_id,
      name: foodItem.name,
      display_order: currentItems.length + 1,
      notes: '',
    };

    setMealDrafts((prev) => ({
      ...prev,
      [mealCode]: [...currentItems, newItem],
    }));
  };

  // Remove Food Item from Meal
  const handleRemoveFoodFromMeal = (mealCode: string, foodItemId: number) => {
    const currentItems = mealDrafts[mealCode] || [];
    const updated = currentItems
      .filter((it) => it.food_item_id !== foodItemId)
      .map((it, idx) => ({ ...it, display_order: idx + 1 }));

    setMealDrafts((prev) => ({ ...prev, [mealCode]: updated }));
  };

  // Reorder Item
  const handleMoveItem = (mealCode: string, index: number, direction: 'up' | 'down') => {
    const currentItems = [...(mealDrafts[mealCode] || [])];
    const targetIndex = direction === 'up' ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= currentItems.length) return;

    const temp = currentItems[index];
    currentItems[index] = currentItems[targetIndex];
    currentItems[targetIndex] = temp;

    const updated = currentItems.map((it, idx) => ({ ...it, display_order: idx + 1 }));
    setMealDrafts((prev) => ({ ...prev, [mealCode]: updated }));
  };

  // Update item note
  const handleItemNoteChange = (mealCode: string, foodItemId: number, note: string) => {
    setMealNotes((prev) => ({
      ...prev,
      [mealCode]: { ...(prev[mealCode] || {}), [foodItemId]: note },
    }));
    setMealDrafts((prev) => ({
      ...prev,
      [mealCode]: (prev[mealCode] || []).map((it) =>
        it.food_item_id === foodItemId ? { ...it, notes: note } : it
      ),
    }));
  };

  // Save Meal to Backend
  const handleSaveMeal = async (mealCode: 'BREAKFAST' | 'LUNCH' | 'EVENING_SNACKS' | 'DINNER') => {
    if (!activeMenu || !selectedDate) return;
    setMealSaving((prev) => ({ ...prev, [mealCode]: true }));
    setMealErrors((prev) => ({ ...prev, [mealCode]: null }));

    const items = (mealDrafts[mealCode] || []).map((it, idx) => ({
      food_item_id: it.food_item_id,
      display_order: idx + 1,
      notes: mealNotes[mealCode]?.[it.food_item_id] || it.notes || '',
    }));

    try {
      const updated = await apiClient.put<MenuStructure>(`/api/v1/menus/${activeMenu.menu_id}/meals`, {
        version: activeMenu.version,
        menu_date: selectedDate,
        meal_type_code: mealCode,
        items,
      });
      setActiveMenu(updated);
    } catch (err: any) {
      if (err.status === 409 || err.code === 'STALE_VERSION' || err.code === 'VERSION_CONFLICT') {
        setConflictDialogOpen(true);
      } else {
        setMealErrors((prev) => ({
          ...prev,
          [mealCode]: err.message || 'Failed to save meal',
        }));
      }
    } finally {
      setMealSaving((prev) => ({ ...prev, [mealCode]: false }));
    }
  };

  // Copy Active Day to Other Days
  const handleCopyDayToDates = async () => {
    if (!activeMenu || copyTargetDates.length === 0) return;
    setCopyingDay(true);

    const activeDay = activeMenu.days.find((d) => d.date === selectedDate);
    if (!activeDay) return;

    try {
      let currentMenu = activeMenu;
      for (const targetDate of copyTargetDates) {
        for (const { code } of MEAL_TYPES) {
          const mealToCopy = activeDay.meals.find((m) => m.meal_type_code === code);
          const items = (mealToCopy?.items || []).map((it, idx) => ({
            food_item_id: it.food_item_id,
            display_order: idx + 1,
            notes: it.notes || '',
          }));

          currentMenu = await apiClient.put<MenuStructure>(`/api/v1/menus/${currentMenu.menu_id}/meals`, {
            version: currentMenu.version,
            menu_date: targetDate,
            meal_type_code: code,
            items,
          });
        }
      }
      setActiveMenu(currentMenu);
      setShowCopyDayModal(false);
      setCopyTargetDates([]);
    } catch (err: any) {
      if (err.status === 409) {
        setConflictDialogOpen(true);
      } else {
        alert(`Failed during copy: ${err.message}`);
      }
    } finally {
      setCopyingDay(false);
    }
  };

  // Publish Menu
  const handlePublishMenu = async () => {
    if (!activeMenu) return;
    setPublishing(true);
    try {
      const res = await apiClient.post<any>(`/api/v1/menus/${activeMenu.menu_id}/publish`, {
        version: activeMenu.version,
      });
      setShowPublishDialog(false);
      if (res.warnings && res.warnings.length > 0) {
        setPublishWarnings(res.warnings);
      }
      if (res.menu) {
        setActiveMenu(res.menu);
      } else {
        await loadMenuDetails(activeMenu.menu_id);
      }
      await fetchMenuList();
    } catch (err: any) {
      if (err.status === 409) {
        setConflictDialogOpen(true);
      } else {
        alert(`Publish failed: ${err.message}`);
      }
    } finally {
      setPublishing(false);
    }
  };

  // Create Food Item Inline
  const handleCreateFoodInline = async () => {
    if (!newFoodName.trim()) return;
    setCreatingFood(true);
    try {
      const created = await apiClient.post<FoodItemMaster>('/api/v1/menus/food-items', {
        name: newFoodName.trim(),
        description: newFoodDesc.trim(),
      });
      setFoodCatalog((prev) => [...prev, created]);
      if (targetMealForNewFood) {
        handleAddFoodToMeal(targetMealForNewFood, created);
      }
      setShowCreateFoodModal(false);
      setNewFoodName('');
      setNewFoodDesc('');
      setTargetMealForNewFood(null);
    } catch (err: any) {
      alert(`Could not create food item: ${err.message}`);
    } finally {
      setCreatingFood(false);
    }
  };

  // Days with no items (for Publish pre-flight)
  const emptyDaysList = useMemo(() => {
    if (!activeMenu) return [];
    return activeMenu.days.filter((d) => {
      const totalItems = d.meals?.reduce((acc, m) => acc + (m.items?.length || 0), 0) || 0;
      return totalItems === 0;
    });
  }, [activeMenu]);

  // Render Month List View
  if (viewMode === 'list') {
    return (
      <div className="space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-text-primary">Monthly Meal Menus</h1>
            <p className="text-sm text-text-secondary mt-1">
              Draft and publish monthly breakfast, lunch, snacks, and dinner schedules for{' '}
              <span className="font-semibold text-text-primary">
                {assignment?.hostel_name || (hostelId ? `Hostel ${hostelId}` : 'your hostel')}
              </span>
            </p>
          </div>
          <Button
            variant="primary"
            icon={<Icons.Plus className="w-4 h-4" />}
            onClick={() => setShowNewMonthModal(true)}
          >
            New Month
          </Button>
        </div>

        {listError && (
          <ErrorState
            errorCode={listError.code}
            message={listError.message}
            traceId={listError.traceId}
            onRetry={fetchMenuList}
          />
        )}

        {loadingList ? (
          <div className="space-y-3">
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        ) : menuList.length === 0 ? (
          <EmptyState
            title="No menus found"
            description="No monthly menus have been drafted for your hostel yet. Click 'New Month' to get started."
            action={{
              label: 'Create First Month Menu',
              onClick: () => setShowNewMonthModal(true),
            }}
          />
        ) : (
          <Card className="p-0 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-sm">
                <thead>
                  <tr className="border-b border-border-default bg-surface-subtle text-text-secondary font-medium">
                    <th className="py-3 px-4">Month</th>
                    <th className="py-3 px-4">Hostel</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Version</th>
                    <th className="py-3 px-4">Published At</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y border-border-default">
                  {menuList.map((m) => {
                    const monthStr = `${m.menu_year}-${String(m.menu_month).padStart(2, '0')}`;
                    return (
                      <tr
                        key={m.menu_id}
                        className="hover:bg-surface-subtle transition-colors cursor-pointer"
                        onClick={() => loadMenuDetails(m.menu_id)}
                      >
                        <td className="py-3 px-4 font-semibold text-text-primary">
                          {monthStr}
                        </td>
                        <td className="py-3 px-4 text-text-secondary">{m.hostel_code || `Hostel ${m.hostel_id}`}</td>
                        <td className="py-3 px-4">
                          <StatusBadge status={m.status} />
                        </td>
                        <td className="py-3 px-4 text-text-secondary">
                          Version {m.version}
                        </td>
                        <td className="py-3 px-4 text-text-secondary">
                          {m.published_at ? new Date(m.published_at).toLocaleDateString() : '—'}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              loadMenuDetails(m.menu_id);
                            }}
                          >
                            Open Editor
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        )}

        {/* New Month Modal */}
        {showNewMonthModal && (
          <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
            <Card className="max-w-md w-full bg-surface-default shadow-xl p-6">
              <div className="flex items-center justify-between border-b border-border-default pb-3">
                <h2 className="text-lg font-bold text-text-primary">Create Monthly Menu</h2>
                <button
                  type="button"
                  onClick={() => setShowNewMonthModal(false)}
                  className="text-text-muted hover:text-text-primary"
                >
                  <Icons.X className="w-5 h-5" />
                </button>
              </div>

              {createMenuError && (
                <div className="mt-3 p-3 text-sm bg-danger-subtle text-danger-contrast rounded border border-danger-default">
                  {createMenuError}
                </div>
              )}

              <div className="mt-4 space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-text-secondary mb-1">Year</label>
                    <input
                      type="number"
                      min={2020}
                      max={2050}
                      value={newMonthYear}
                      onChange={(e) => setNewMonthYear(parseInt(e.target.value) || new Date().getFullYear())}
                      className="w-full px-3 py-2 border border-border-default rounded bg-surface-default text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-primary-focus"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-text-secondary mb-1">Month</label>
                    <select
                      value={newMonthMonth}
                      onChange={(e) => setNewMonthMonth(parseInt(e.target.value))}
                      className="w-full px-3 py-2 border border-border-default rounded bg-surface-default text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-primary-focus"
                    >
                      {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                        <option key={m} value={m}>
                          {new Date(2000, m - 1, 1).toLocaleString('default', { month: 'long' })} ({m})
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="flex items-center gap-2 pt-2">
                  <input
                    type="checkbox"
                    id="copyPrevious"
                    checked={copyPreviousPattern}
                    onChange={(e) => setCopyPreviousPattern(e.target.checked)}
                    className="h-4 w-4 rounded border-border-default text-primary-default focus:ring-primary-focus"
                  />
                  <label htmlFor="copyPrevious" className="text-sm text-text-primary">
                    Copy previous month's weekday pattern
                  </label>
                </div>
                <p className="text-xs text-text-muted">
                  If selected, the initial draft will duplicate the weekday meal plans from the previous month.
                </p>
              </div>

              <div className="mt-6 flex justify-end gap-2 border-t border-border-default pt-3">
                <Button variant="ghost" onClick={() => setShowNewMonthModal(false)} disabled={creatingMenu}>
                  Cancel
                </Button>
                <Button variant="primary" onClick={handleCreateMenu} loading={creatingMenu}>
                  Create Draft Menu
                </Button>
              </div>
            </Card>
          </div>
        )}
      </div>
    );
  }

  // Render Editor View
  if (!activeMenu && loadingMenu) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (menuError) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" icon={<Icons.ChevronLeft className="w-4 h-4" />} onClick={() => setViewMode('list')}>
          Back to Month List
        </Button>
        <ErrorState
          errorCode={menuError.code}
          message={menuError.message}
          traceId={menuError.traceId}
          onRetry={() => selectedMenuId && loadMenuDetails(selectedMenuId)}
        />
      </div>
    );
  }

  if (!activeMenu) return null;

  const currentDay = activeMenu.days.find((d) => d.date === selectedDate);

  return (
    <div className="space-y-6">
      {/* Top Header Bar */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-border-default pb-4">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            icon={<Icons.ChevronLeft className="w-4 h-4" />}
            onClick={() => {
              setViewMode('list');
              fetchMenuList();
            }}
          >
            Back
          </Button>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold text-text-primary">
                {activeMenu.month_label || `${activeMenu.year}-${String(activeMenu.month).padStart(2, '0')}`} Menu
              </h1>
              <StatusBadge status={activeMenu.status} />
              <span className="text-xs bg-surface-subtle text-text-secondary px-2 py-0.5 rounded border border-border-default">
                {activeMenu.hostel_name || activeMenu.hostel_code}
              </span>
            </div>
            <p className="text-xs text-text-secondary mt-0.5">
              Version {activeMenu.version} • {calculateDaysFilled(activeMenu.days)}
              {activeMenu.published_at && ` • Published on ${new Date(activeMenu.published_at).toLocaleString()}`}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            icon={<Icons.Eye className="w-4 h-4" />}
            onClick={() => setShowPreviewModal(true)}
          >
            Preview as Student
          </Button>

          {activeMenu.status === 'DRAFT' && (
            <Button
              variant="primary"
              size="sm"
              icon={<Icons.CheckCircle className="w-4 h-4" />}
              onClick={() => setShowPublishDialog(true)}
            >
              Publish Menu
            </Button>
          )}
        </div>
      </div>

      {/* Published Notice Banner */}
      {activeMenu.status === 'PUBLISHED' && (
        <div className="bg-primary-subtle border border-primary-default text-primary-contrast px-4 py-3 rounded text-sm flex items-start gap-3">
          <Icons.Info className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold">Notice:</span> This menu is published. Later edits are audited as{' '}
            <code className="text-xs bg-white/40 px-1 py-0.5 rounded font-mono">MENU_REVISED</code> and become visible
            to students immediately.
          </div>
        </div>
      )}

      {publishWarnings.length > 0 && (
        <div className="bg-warning-subtle border border-warning-default text-warning-contrast px-4 py-3 rounded text-sm">
          <p className="font-semibold mb-1">Publication Notes:</p>
          <ul className="list-disc list-inside space-y-0.5 text-xs">
            {publishWarnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Main Grid: Left Calendar / Right Day Editor */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
        {/* Left Column: Calendar Grid */}
        <div className="md:col-span-4 lg:col-span-3 space-y-3">
          <Card className="p-3">
            <div className="flex items-center justify-between pb-2 border-b border-border-default mb-2">
              <span className="text-xs font-bold text-text-primary uppercase tracking-wider">Month Days</span>
              <div className="flex items-center gap-2 text-[10px] text-text-muted">
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-surface-subtle border border-border-default" /> Empty
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-amber-400" /> Partial
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-emerald-500" /> Done
                </span>
              </div>
            </div>

            <div className="grid grid-cols-7 gap-1 text-center">
              {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((day, idx) => (
                <div key={idx} className="text-[11px] font-semibold text-text-muted py-1">
                  {day}
                </div>
              ))}

              {/* Pad blank days before the 1st */}
              {activeMenu.days.length > 0 &&
                Array.from({ length: new Date(activeMenu.days[0].date).getDay() }).map((_, i) => (
                  <div key={`blank-${i}`} className="p-2" />
                ))}

              {/* Day cells */}
              {activeMenu.days.map((d) => {
                const dayNum = parseInt(d.date.split('-')[2]);
                const status = getDayStatus(d);
                const isSelected = d.date === selectedDate;

                let indicatorColor = 'bg-surface-subtle text-text-muted border-border-default';
                if (status === 'partial') indicatorColor = 'bg-amber-100 text-amber-800 border-amber-300';
                if (status === 'complete') indicatorColor = 'bg-emerald-100 text-emerald-800 border-emerald-300';

                return (
                  <button
                    key={d.date}
                    type="button"
                    onClick={() => setSelectedDate(d.date)}
                    className={cn(
                      'p-2 rounded text-xs font-medium border flex flex-col items-center justify-center transition-all',
                      isSelected
                        ? 'ring-2 ring-primary-focus border-primary-default bg-primary-subtle text-primary-contrast font-bold'
                        : indicatorColor,
                      'hover:scale-105 active:scale-95'
                    )}
                    aria-label={`Select date ${d.date}`}
                  >
                    <span>{dayNum}</span>
                  </button>
                );
              })}
            </div>

            <div className="mt-3 pt-3 border-t border-border-default">
              <Button
                variant="secondary"
                size="sm"
                className="w-full text-xs"
                icon={<Icons.Copy className="w-3.5 h-3.5" />}
                onClick={() => {
                  setCopyTargetDates([]);
                  setShowCopyDayModal(true);
                }}
              >
                Copy Day to Other Dates
              </Button>
            </div>
          </Card>
        </div>

        {/* Right Column: Day Editor */}
        <div className="md:col-span-8 lg:col-span-9 space-y-4">
          <div className="flex items-center justify-between bg-surface-subtle px-4 py-2.5 rounded-lg border border-border-default">
            <div>
              <h2 className="text-base font-bold text-text-primary">
                {selectedDate
                  ? new Date(selectedDate + 'T00:00:00').toLocaleDateString(undefined, {
                      weekday: 'long',
                      year: 'numeric',
                      month: 'short',
                      day: 'numeric',
                    })
                  : 'Select a Day'}
              </h2>
              <span className="text-xs text-text-secondary">
                Configure Breakfast, Lunch, Evening Snacks, and Dinner for this day
              </span>
            </div>
            {currentDay && (
              <span className="text-xs font-medium text-text-secondary">
                Coverage:{' '}
                <span
                  className={cn(
                    'font-bold capitalize',
                    getDayStatus(currentDay) === 'complete' ? 'text-emerald-600' : 'text-amber-600'
                  )}
                >
                  {getDayStatus(currentDay)}
                </span>
              </span>
            )}
          </div>

          {/* 4 Meal Cards */}
          <div className="space-y-4">
            {MEAL_TYPES.map(({ code, name }) => {
              const items = mealDrafts[code] || [];
              const isSaving = mealSaving[code] || false;
              const errorMsg = mealErrors[code];

              return (
                <Card key={code} className="p-4 border border-border-default">
                  <div className="flex items-center justify-between border-b border-border-default pb-3">
                    <div className="flex items-center gap-2">
                      <span className="w-3 h-3 rounded-full bg-primary-default" />
                      <h3 className="text-base font-bold text-text-primary">{name}</h3>
                      <span className="text-xs text-text-muted">({items.length} items)</span>
                    </div>

                    <Button
                      variant="primary"
                      size="sm"
                      loading={isSaving}
                      onClick={() => handleSaveMeal(code)}
                    >
                      Save {name}
                    </Button>
                  </div>

                  {errorMsg && (
                    <div className="mt-3 p-2 text-xs bg-danger-subtle text-danger-contrast rounded border border-danger-default flex items-center justify-between">
                      <span>{errorMsg}</span>
                      <button
                        type="button"
                        onClick={() => setMealErrors((prev) => ({ ...prev, [code]: null }))}
                        className="text-xs font-bold"
                      >
                        Dismiss
                      </button>
                    </div>
                  )}

                  {/* Food Items List */}
                  <div className="mt-3 space-y-2">
                    {items.length === 0 ? (
                      <p className="text-xs text-text-muted italic py-2">
                        No food items added yet. Search below to add items to {name.toLowerCase()}.
                      </p>
                    ) : (
                      items.map((item, idx) => (
                        <div
                          key={`${item.food_item_id}-${idx}`}
                          className="flex items-center gap-2 p-2 bg-surface-subtle rounded border border-border-default text-xs"
                        >
                          <div className="flex flex-col gap-0.5">
                            <button
                              type="button"
                              disabled={idx === 0}
                              onClick={() => handleMoveItem(code, idx, 'up')}
                              className="text-text-muted hover:text-text-primary disabled:opacity-20"
                              aria-label="Move item up"
                            >
                              <Icons.ChevronUp className="w-3 h-3" />
                            </button>
                            <button
                              type="button"
                              disabled={idx === items.length - 1}
                              onClick={() => handleMoveItem(code, idx, 'down')}
                              className="text-text-muted hover:text-text-primary disabled:opacity-20"
                              aria-label="Move item down"
                            >
                              <Icons.ChevronDown className="w-3 h-3" />
                            </button>
                          </div>

                          <span className="font-semibold text-text-primary flex-1">{item.name}</span>

                          <input
                            type="text"
                            placeholder="Optional notes"
                            value={mealNotes[code]?.[item.food_item_id] ?? (item.notes || '')}
                            onChange={(e) => handleItemNoteChange(code, item.food_item_id, e.target.value)}
                            className="w-48 px-2 py-1 text-xs border border-border-default rounded bg-surface-default text-text-primary focus:outline-none focus:ring-1 focus:ring-primary-focus"
                          />

                          <button
                            type="button"
                            onClick={() => handleRemoveFoodFromMeal(code, item.food_item_id)}
                            className="text-danger-default hover:text-danger-contrast p-1"
                            aria-label={`Remove ${item.name}`}
                          >
                            <Icons.Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      ))
                    )}
                  </div>

                  {/* Add Food Item Controls */}
                  <div className="mt-3 pt-3 border-t border-border-default flex flex-col sm:flex-row items-center gap-2">
                    <div className="relative flex-1 w-full">
                      <select
                        onChange={(e) => {
                          const id = parseInt(e.target.value);
                          if (!id) return;
                          const found = foodCatalog.find((f) => f.food_item_id === id);
                          if (found) {
                            handleAddFoodToMeal(code, found);
                          }
                          e.target.value = '';
                        }}
                        className="w-full px-3 py-1.5 text-xs border border-border-default rounded bg-surface-default text-text-primary focus:outline-none focus:ring-1 focus:ring-primary-focus"
                        defaultValue=""
                      >
                        <option key="placeholder" value="" disabled>
                          + Select food item from catalog to add...
                        </option>
                        {foodCatalog
                          .filter((f) => f.status !== 'INACTIVE')
                          .map((f, idx) => (
                            <option key={`food-${f.food_item_id}-${idx}`} value={f.food_item_id}>
                              {f.name}
                            </option>
                          ))}
                      </select>
                    </div>

                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-xs whitespace-nowrap"
                      icon={<Icons.Plus className="w-3.5 h-3.5" />}
                      onClick={() => {
                        setTargetMealForNewFood(code);
                        setShowCreateFoodModal(true);
                      }}
                    >
                      New Item
                    </Button>
                  </div>
                </Card>
              );
            })}
          </div>
        </div>
      </div>

      {/* Copy Day Modal */}
      {showCopyDayModal && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <Card className="max-w-lg w-full bg-surface-default shadow-xl p-6">
            <div className="flex items-center justify-between border-b border-border-default pb-3">
              <div>
                <h2 className="text-base font-bold text-text-primary">Copy Day Menu</h2>
                <p className="text-xs text-text-secondary mt-0.5">
                  Copy meals from <span className="font-semibold text-text-primary">{selectedDate}</span> to target days.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowCopyDayModal(false)}
                className="text-text-muted hover:text-text-primary"
              >
                <Icons.X className="w-5 h-5" />
              </button>
            </div>

            <div className="mt-4 space-y-3 max-h-80 overflow-y-auto">
              <span className="text-xs font-semibold text-text-secondary">Select target dates in this month:</span>
              <div className="grid grid-cols-4 gap-2">
                {activeMenu.days
                  .filter((d) => d.date !== selectedDate)
                  .map((d) => {
                    const isChecked = copyTargetDates.includes(d.date);
                    return (
                      <label
                        key={d.date}
                        className={cn(
                          'flex items-center gap-1.5 p-2 rounded border text-xs cursor-pointer transition-colors',
                          isChecked ? 'bg-primary-subtle border-primary-default' : 'border-border-default'
                        )}
                      >
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setCopyTargetDates((prev) => [...prev, d.date]);
                            } else {
                              setCopyTargetDates((prev) => prev.filter((dt) => dt !== d.date));
                            }
                          }}
                          className="h-3.5 w-3.5 text-primary-default rounded"
                        />
                        <span>{d.date.slice(5)}</span>
                      </label>
                    );
                  })}
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-2 border-t border-border-default pt-3">
              <Button variant="ghost" onClick={() => setShowCopyDayModal(false)} disabled={copyingDay}>
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleCopyDayToDates}
                loading={copyingDay}
                disabled={copyTargetDates.length === 0}
              >
                Copy to {copyTargetDates.length} Days
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* Publish Dialog */}
      {showPublishDialog && (
        <ConfirmDialog
          isOpen={showPublishDialog}
          title="Publish Monthly Menu"
          description={
            emptyDaysList.length > 0
              ? `Warning: ${emptyDaysList.length} days in this month have no items scheduled. Are you sure you want to publish this menu to students?`
              : `Are you sure you want to publish the menu for ${activeMenu.month_label || `${activeMenu.year}-${activeMenu.month}`} to students?`
          }
          confirmLabel="Yes, Publish Menu"
          variant="primary"
          loading={publishing}
          onConfirm={handlePublishMenu}
          onClose={() => setShowPublishDialog(false)}
        />
      )}

      {/* Optimistic Concurrency Conflict Dialog */}
      {conflictDialogOpen && (
        <ConfirmDialog
          isOpen={conflictDialogOpen}
          title="Version Conflict (409 Conflict)"
          description="This menu was modified by another session or administrator while you were editing it. Please reload the latest version to prevent overwriting changes."
          confirmLabel="Reload Latest Menu"
          variant="danger"
          onConfirm={() => {
            setConflictDialogOpen(false);
            if (activeMenu) loadMenuDetails(activeMenu.menu_id);
          }}
          onClose={() => setConflictDialogOpen(false)}
        />
      )}

      {/* Student Preview Modal */}
      {showPreviewModal && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <Card className="max-w-2xl w-full max-h-[90vh] bg-surface-default flex flex-col shadow-2xl p-0 overflow-hidden">
            <div className="flex items-center justify-between border-b border-border-default pb-3 px-6 pt-4">
              <div>
                <h2 className="text-lg font-bold text-text-primary">Preview as Student</h2>
                <p className="text-xs text-text-secondary">
                  How students view this menu in the mobile app
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowPreviewModal(false)}
                className="text-text-muted hover:text-text-primary"
              >
                <Icons.X className="w-5 h-5" />
              </button>
            </div>

            <div className="overflow-y-auto p-6 space-y-6 flex-1">
              {activeMenu.days.map((day) => (
                <div key={day.date} className="border border-border-default rounded-lg p-4 bg-surface-subtle">
                  <h3 className="font-bold text-sm text-text-primary border-b border-border-default pb-2 mb-3">
                    {new Date(day.date + 'T00:00:00').toLocaleDateString(undefined, {
                      weekday: 'long',
                      month: 'short',
                      day: 'numeric',
                    })}
                  </h3>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                    {MEAL_TYPES.map(({ code, name }) => {
                      const meal = day.meals?.find((m) => m.meal_type_code === code);
                      const hasItems = meal && meal.items && meal.items.length > 0;
                      return (
                        <div key={code} className="p-2 bg-surface-default rounded border border-border-default">
                          <span className="font-bold text-text-primary block mb-1">{name}</span>
                          {hasItems ? (
                            <ul className="space-y-0.5 text-text-secondary">
                              {meal.items.map((it) => (
                                <li key={it.food_item_id} className="flex justify-between">
                                  <span>{it.name}</span>
                                  {it.notes && <span className="text-text-muted text-[10px] italic">({it.notes})</span>}
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <span className="text-text-muted italic text-[11px]">Not scheduled</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>

            <div className="border-t border-border-default p-4 flex justify-end">
              <Button variant="secondary" onClick={() => setShowPreviewModal(false)}>
                Close Preview
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* Inline Create Food Master Modal */}
      {showCreateFoodModal && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <Card className="max-w-md w-full bg-surface-default shadow-xl p-6">
            <div className="flex items-center justify-between border-b border-border-default pb-3">
              <h2 className="text-base font-bold text-text-primary">Add Food Item to Master Catalog</h2>
              <button
                type="button"
                onClick={() => setShowCreateFoodModal(false)}
                className="text-text-muted hover:text-text-primary"
              >
                <Icons.X className="w-5 h-5" />
              </button>
            </div>

            <div className="mt-4 space-y-3">
              <div>
                <label className="block text-xs font-semibold text-text-secondary mb-1">
                  Item Name <span className="text-danger-default">*</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. Masala Dosa"
                  value={newFoodName}
                  onChange={(e) => setNewFoodName(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-border-default rounded bg-surface-default text-text-primary focus:outline-none focus:ring-1 focus:ring-primary-focus"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-text-secondary mb-1">Description (Optional)</label>
                <textarea
                  placeholder="e.g. Served with coconut chutney and sambar"
                  rows={2}
                  value={newFoodDesc}
                  onChange={(e) => setNewFoodDesc(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-border-default rounded bg-surface-default text-text-primary focus:outline-none focus:ring-1 focus:ring-primary-focus"
                />
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-2 border-t border-border-default pt-3">
              <Button variant="ghost" onClick={() => setShowCreateFoodModal(false)} disabled={creatingFood}>
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleCreateFoodInline}
                loading={creatingFood}
                disabled={!newFoodName.trim()}
              >
                Add & Include in Meal
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
};

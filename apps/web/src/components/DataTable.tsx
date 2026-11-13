import React, { useState } from 'react';
import { cn } from '../lib/utils';
import { Icons } from './Icons';
import { Checkbox } from './Checkbox';
import { EmptyState } from './EmptyState';

export interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => React.ReactNode;
  sortable?: boolean;
  align?: 'left' | 'center' | 'right';
  width?: string;
}

export interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyExtractor: (row: T) => string;
  selectable?: boolean;
  selectedKeys?: Set<string>;
  onSelectionChange?: (selectedKeys: Set<string>) => void;
  sortColumn?: string;
  sortDirection?: 'asc' | 'desc';
  onSort?: (columnKey: string) => void;
  emptyTitle?: string;
  emptyDescription?: string;
  stickyHeader?: boolean;
  dense?: boolean;
  className?: string;
}

export function DataTable<T>({
  columns,
  data,
  keyExtractor,
  selectable = false,
  selectedKeys = new Set(),
  onSelectionChange,
  sortColumn,
  sortDirection,
  onSort,
  emptyTitle = 'No records found',
  emptyDescription = 'There are no items to display right now.',
  stickyHeader = true,
  dense = false,
  className,
}: DataTableProps<T>) {
  const [visibleColumns, setVisibleColumns] = useState<Set<string>>(
    new Set(columns.map((c) => c.key))
  );
  const [showColumnMenu, setShowColumnMenu] = useState(false);

  const activeColumns = columns.filter((c) => visibleColumns.has(c.key));

  const allSelected =
    data.length > 0 && data.every((row) => selectedKeys.has(keyExtractor(row)));

  const handleSelectAll = () => {
    if (allSelected) {
      onSelectionChange?.(new Set());
    } else {
      onSelectionChange?.(new Set(data.map(keyExtractor)));
    }
  };

  const handleSelectRow = (key: string) => {
    const next = new Set(selectedKeys);
    if (next.has(key)) {
      next.delete(key);
    } else {
      next.add(key);
    }
    onSelectionChange?.(next);
  };

  const toggleColumn = (key: string) => {
    const next = new Set(visibleColumns);
    if (next.has(key)) {
      if (next.size > 1) next.delete(key);
    } else {
      next.add(key);
    }
    setVisibleColumns(next);
  };

  return (
    <div className={cn('w-full border border-border rounded-[10px] bg-surface overflow-hidden', className)}>
      {/* Table Toolbar / Column Menu */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-bg/50">
        <span className="text-[12px] font-medium text-text-secondary tabular-nums">
          Showing {data.length} records {selectedKeys.size > 0 && `(${selectedKeys.size} selected)`}
        </span>
        <div className="relative">
          <button
            type="button"
            onClick={() => setShowColumnMenu(!showColumnMenu)}
            className="inline-flex items-center gap-1.5 text-[12px] font-medium text-text px-2 py-1 rounded border border-border bg-white hover:bg-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <Icons.Filter className="w-3.5 h-3.5" />
            <span>Columns</span>
          </button>
          {showColumnMenu && (
            <div className="absolute right-0 mt-1 w-48 bg-white border border-border rounded-[6px] shadow-menu p-2 z-20 flex flex-col gap-1.5">
              <span className="text-[11px] font-semibold text-text-muted uppercase px-1">Visible Columns</span>
              {columns.map((col) => (
                <label key={col.key} className="flex items-center gap-2 text-[12px] px-1 py-0.5 cursor-pointer hover:bg-bg rounded">
                  <input
                    type="checkbox"
                    checked={visibleColumns.has(col.key)}
                    onChange={() => toggleColumn(col.key)}
                    className="accent-primary"
                  />
                  <span>{col.header}</span>
                </label>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Table Container */}
      <div className="overflow-x-auto max-h-[600px]">
        <table className="w-full border-collapse text-left">
          <thead className={cn('bg-bg border-b border-border-strong', stickyHeader && 'sticky top-0 z-10')}>
            <tr>
              {selectable && (
                <th className="w-10 px-4 py-3 text-center">
                  <Checkbox
                    aria-label="Select all rows"
                    checked={allSelected}
                    onChange={handleSelectAll}
                  />
                </th>
              )}
              {activeColumns.map((col) => (
                <th
                  key={col.key}
                  style={{ width: col.width }}
                  onClick={() => col.sortable && onSort?.(col.key)}
                  className={cn(
                    'px-4 py-3 text-[13px] font-semibold text-text select-none',
                    col.sortable && 'cursor-pointer hover:bg-[#E2E8F0]/50 transition-colors',
                    col.align === 'right' && 'text-right',
                    col.align === 'center' && 'text-center'
                  )}
                >
                  <div className={cn('inline-flex items-center gap-1.5', col.align === 'right' && 'justify-end')}>
                    <span>{col.header}</span>
                    {col.sortable && sortColumn === col.key && (
                      sortDirection === 'asc' ? (
                        <Icons.ChevronUp className="w-3.5 h-3.5 text-primary" />
                      ) : (
                        <Icons.ChevronDown className="w-3.5 h-3.5 text-primary" />
                      )
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {data.length === 0 ? (
              <tr>
                <td colSpan={activeColumns.length + (selectable ? 1 : 0)} className="p-8">
                  <EmptyState title={emptyTitle} description={emptyDescription} />
                </td>
              </tr>
            ) : (
              data.map((row) => {
                const key = keyExtractor(row);
                const isSelected = selectedKeys.has(key);
                return (
                  <tr
                    key={key}
                    className={cn(
                      'transition-colors hover:bg-bg/80',
                      isSelected && 'bg-primary-subtle',
                      dense ? 'text-[13px] leading-[18px]' : 'text-[14px] leading-[20px]'
                    )}
                  >
                    {selectable && (
                      <td className="px-4 py-3 text-center">
                        <Checkbox
                          aria-label={`Select row ${key}`}
                          checked={isSelected}
                          onChange={() => handleSelectRow(key)}
                        />
                      </td>
                    )}
                    {activeColumns.map((col) => (
                      <td
                        key={col.key}
                        className={cn(
                          dense ? 'px-4 py-2' : 'px-4 py-3',
                          'text-text tabular-nums',
                          col.align === 'right' && 'text-right',
                          col.align === 'center' && 'text-center'
                        )}
                      >
                        {col.render ? col.render(row) : (row as Record<string, any>)[col.key]}
                      </td>
                    ))}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}


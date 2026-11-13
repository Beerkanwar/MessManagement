import React from 'react';
import { cn } from '../lib/utils';
import { Icons } from './Icons';

export interface FilterBarProps {
  searchQuery?: string;
  onSearchChange?: (val: string) => void;
  searchPlaceholder?: string;
  filters?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}

export const FilterBar: React.FC<FilterBarProps> = ({
  searchQuery = '',
  onSearchChange,
  searchPlaceholder = 'Search...',
  filters,
  actions,
  className,
}) => {
  return (
    <div
      className={cn(
        'w-full flex flex-col md:flex-row md:items-center justify-between gap-3 p-3 bg-surface border border-border rounded-[8px]',
        className
      )}
    >
      <div className="flex-1 flex flex-wrap items-center gap-2.5">
        {onSearchChange && (
          <div className="relative min-w-[220px] max-w-sm flex-1">
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none">
              <Icons.Search className="w-4 h-4" />
            </div>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder={searchPlaceholder}
              className="w-full h-[38px] pl-9 pr-3 text-[13px] bg-bg border border-border rounded-[6px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1 text-text placeholder:text-text-muted"
            />
          </div>
        )}
        {filters}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  );
};


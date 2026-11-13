import React from 'react';
import { cn } from '../lib/utils';

export interface TabItem {
  key: string;
  label: string;
  count?: number;
  disabled?: boolean;
}

export interface TabsProps {
  items: TabItem[];
  activeKey: string;
  onChange: (key: string) => void;
  className?: string;
}

export const Tabs: React.FC<TabsProps> = ({ items, activeKey, onChange, className }) => {
  return (
    <div className={cn('border-b border-border w-full flex items-center gap-6 select-none', className)}>
      {items.map((tab) => {
        const isActive = tab.key === activeKey;
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={isActive}
            disabled={tab.disabled}
            onClick={() => !tab.disabled && onChange(tab.key)}
            className={cn(
              'relative py-3 text-[14px] leading-[20px] font-medium transition-colors flex items-center gap-2 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded-t',
              isActive
                ? 'text-primary font-semibold'
                : 'text-text-secondary hover:text-text',
              tab.disabled && 'opacity-40 cursor-not-allowed'
            )}
          >
            <span>{tab.label}</span>
            {typeof tab.count === 'number' && (
              <span
                className={cn(
                  'px-2 py-0.5 text-[11px] font-bold rounded-full tabular-nums',
                  isActive ? 'bg-primary-subtle text-primary border border-primary-border' : 'bg-bg text-text-muted border border-border'
                )}
              >
                {tab.count}
              </span>
            )}
            {isActive && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary rounded-t-full" />
            )}
          </button>
        );
      })}
    </div>
  );
};


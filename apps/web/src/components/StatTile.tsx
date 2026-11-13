import React from 'react';
import { cn } from '../lib/utils';

export interface StatTileProps {
  label: string;
  value: string | number;
  change?: string;
  changeType?: 'positive' | 'negative' | 'neutral';
  icon?: React.ReactNode;
  href?: string;
  className?: string;
  onClick?: () => void;
}

export const StatTile: React.FC<StatTileProps> = ({
  label,
  value,
  change,
  changeType = 'neutral',
  icon,
  href,
  className,
  onClick,
}) => {
  const content = (
    <div
      onClick={onClick}
      className={cn(
        'bg-surface border border-border rounded-[10px] p-5 flex flex-col justify-between transition-colors',
        (href || onClick) && 'hover:border-primary-border hover:bg-primary-subtle cursor-pointer',
        className
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-[13px] leading-[18px] font-medium text-text-secondary">{label}</span>
        {icon && <div className="text-text-muted">{icon}</div>}
      </div>
      <div className="mt-3 flex items-baseline gap-2">
        <span className="text-[28px] font-bold text-text tabular-nums">{value}</span>
        {change && (
          <span
            className={cn(
              'text-[12px] font-medium',
              changeType === 'positive' && 'text-success',
              changeType === 'negative' && 'text-danger',
              changeType === 'neutral' && 'text-text-muted'
            )}
          >
            {change}
          </span>
        )}
      </div>
    </div>
  );

  if (href) {
    return (
      <a href={href} className="no-underline block">
        {content}
      </a>
    );
  }

  return content;
};


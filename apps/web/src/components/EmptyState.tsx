import React from 'react';
import { cn } from '../lib/utils';
import { Icons } from './Icons';

export interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title,
  description,
  icon,
  action,
  className,
}) => {
  return (
    <div className={cn('flex flex-col items-center justify-center p-8 text-center max-w-sm mx-auto select-none', className)}>
      <div className="w-12 h-12 rounded-full bg-bg border border-border flex items-center justify-center text-text-muted mb-3">
        {icon || <Icons.Info className="w-6 h-6 stroke-[1.5]" />}
      </div>
      <h4 className="text-[16px] leading-[24px] font-semibold text-text">{title}</h4>
      {description && <p className="text-[13px] leading-[18px] text-text-secondary mt-1">{description}</p>}
      {action && (
        <button
          type="button"
          onClick={action.onClick}
          className="mt-4 px-4 py-2 text-[13px] font-medium text-white bg-primary hover:bg-primary-hover rounded-[6px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
        >
          {action.label}
        </button>
      )}
    </div>
  );
};


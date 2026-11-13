import React from 'react';
import { cn } from '../lib/utils';
import { Icons } from './Icons';

export interface BannerProps {
  type: 'info' | 'warning' | 'danger';
  title?: string;
  message: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

export const Banner: React.FC<BannerProps> = ({
  type,
  title,
  message,
  action,
  className,
}) => {
  const styles = {
    info: {
      bg: 'bg-info-subtle',
      border: 'border-[#BFDBFE]',
      text: 'text-[#1E40AF]',
      icon: <Icons.Info className="w-5 h-5 text-info shrink-0" />,
    },
    warning: {
      bg: 'bg-warning-subtle',
      border: 'border-[#FDE68A]',
      text: 'text-[#92400E]',
      icon: <Icons.AlertTriangle className="w-5 h-5 text-warning shrink-0" />,
    },
    danger: {
      bg: 'bg-danger-subtle',
      border: 'border-[#FECACA]',
      text: 'text-[#991B1B]',
      icon: <Icons.XCircle className="w-5 h-5 text-danger shrink-0" />,
    },
  };

  const current = styles[type];

  return (
    <div
      role="alert"
      className={cn(
        'w-full p-4 rounded-[8px] border flex items-start gap-3 select-none',
        current.bg,
        current.border,
        className
      )}
    >
      {current.icon}
      <div className="flex-1 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div>
          {title && <span className={cn('block font-semibold text-[14px]', current.text)}>{title}</span>}
          <span className={cn('text-[13px] leading-[18px]', current.text)}>{message}</span>
        </div>
        {action && (
          <button
            type="button"
            onClick={action.onClick}
            className={cn(
              'text-[13px] font-semibold underline underline-offset-2 shrink-0 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded px-1',
              current.text
            )}
          >
            {action.label}
          </button>
        )}
      </div>
    </div>
  );
};


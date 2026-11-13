import React, { useEffect } from 'react';
import { cn } from '../lib/utils';
import { Icons } from './Icons';

export interface ToastProps {
  id?: string;
  type?: 'success' | 'warning' | 'danger' | 'info';
  title?: string;
  message: string;
  duration?: number;
  onDismiss?: () => void;
  className?: string;
}

export const Toast: React.FC<ToastProps> = ({
  type = 'info',
  title,
  message,
  duration = 4000,
  onDismiss,
  className,
}) => {
  useEffect(() => {
    if (duration > 0 && onDismiss) {
      const timer = setTimeout(() => {
        onDismiss();
      }, duration);
      return () => clearTimeout(timer);
    }
  }, [duration, onDismiss]);

  const styles = {
    success: {
      bg: 'bg-surface',
      border: 'border-success',
      icon: <Icons.CheckCircle className="w-5 h-5 text-success shrink-0" />,
    },
    warning: {
      bg: 'bg-surface',
      border: 'border-warning',
      icon: <Icons.AlertTriangle className="w-5 h-5 text-warning shrink-0" />,
    },
    danger: {
      bg: 'bg-surface',
      border: 'border-danger',
      icon: <Icons.XCircle className="w-5 h-5 text-danger shrink-0" />,
    },
    info: {
      bg: 'bg-surface',
      border: 'border-info',
      icon: <Icons.Info className="w-5 h-5 text-info shrink-0" />,
    },
  };

  const current = styles[type];

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'flex items-start gap-3 p-4 rounded-[8px] border-l-4 shadow-lg bg-surface max-w-sm w-full select-none border-t border-r border-b border-border',
        current.border,
        className
      )}
    >
      {current.icon}
      <div className="flex-1 overflow-hidden">
        {title && <h5 className="text-[14px] font-semibold text-text mb-0.5">{title}</h5>}
        <p className="text-[13px] leading-[18px] text-text-secondary">{message}</p>
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss toast"
          className="text-text-muted hover:text-text p-1 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          <Icons.X className="w-4 h-4" />
        </button>
      )}
    </div>
  );
};


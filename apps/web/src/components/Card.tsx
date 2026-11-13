import React from 'react';
import { cn } from '../lib/utils';

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  title?: string;
  subtitle?: string;
  actions?: React.ReactNode;
}

export const Card: React.FC<CardProps> = ({
  title,
  subtitle,
  actions,
  children,
  className,
  ...props
}) => {
  return (
    <div
      className={cn(
        'bg-surface border border-border rounded-[10px] overflow-hidden transition-all',
        className
      )}
      {...props}
    >
      {(title || subtitle || actions) && (
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div>
            {title && <h3 className="text-[16px] leading-[24px] font-semibold text-text">{title}</h3>}
            {subtitle && <p className="text-[13px] leading-[18px] text-text-secondary mt-0.5">{subtitle}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className="p-6">{children}</div>
    </div>
  );
};


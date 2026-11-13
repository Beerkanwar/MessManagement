import React from 'react';
import { cn } from '../lib/utils';
import { Icons } from './Icons';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  icon?: React.ReactNode;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'primary', size = 'md', loading = false, disabled, icon, children, ...props }, ref) => {
    const baseStyles =
      'inline-flex items-center justify-center font-medium transition-colors duration-150 rounded-[6px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer select-none';

    const variantStyles = {
      primary: 'bg-primary text-white hover:bg-[#115E59] active:bg-[#0D625B]',
      secondary: 'bg-white text-text border border-border hover:bg-bg active:bg-[#EDF2F7]',
      ghost: 'bg-transparent text-text hover:bg-bg hover:text-text active:bg-[#EDF2F7]',
      danger: 'bg-danger text-white hover:bg-[#991B1B] active:bg-[#7F1D1D]',
    };

    const sizeStyles = {
      sm: 'min-h-[36px] px-3 py-1.5 text-[13px] leading-[18px] gap-1.5',
      md: 'min-h-[44px] px-4 py-2 text-[14px] leading-[20px] gap-2',
      lg: 'min-h-[52px] px-6 py-3 text-[16px] leading-[24px] gap-2.5',
    };

    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        aria-busy={loading}
        aria-disabled={disabled || loading}
        className={cn(baseStyles, variantStyles[variant], sizeStyles[size], className)}
        {...props}
      >
        {loading ? (
          <Icons.RefreshCw className="w-4 h-4 animate-spin text-current" />
        ) : (
          icon
        )}
        <span>{children}</span>
      </button>
    );
  }
);
Button.displayName = 'Button';


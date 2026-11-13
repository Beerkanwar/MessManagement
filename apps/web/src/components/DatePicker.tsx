import React, { useId } from 'react';
import { cn } from '../lib/utils';
import { Icons } from './Icons';

export interface DatePickerProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label?: string;
  helperText?: string;
  error?: string;
}

export const DatePicker = React.forwardRef<HTMLInputElement, DatePickerProps>(
  ({ className, label, helperText, error, id, ...props }, ref) => {
    const generatedId = useId();
    const inputId = id || generatedId;

    return (
      <div className="w-full flex flex-col gap-1.5 text-left">
        {label && (
          <label htmlFor={inputId} className="text-[13px] leading-[18px] font-medium text-text">
            {label}
            {props.required && <span className="text-danger ml-0.5">*</span>}
          </label>
        )}
        <div className="relative flex items-center">
          <input
            id={inputId}
            ref={ref}
            type="date"
            className={cn(
              'w-full min-h-[44px] px-3 py-2 text-[14px] leading-[20px] text-text bg-white border rounded-[6px] transition-colors',
              error ? 'border-danger focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger' : 'border-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
              'disabled:bg-bg disabled:text-text-muted disabled:cursor-not-allowed',
              className
            )}
            {...props}
          />
          <div className="absolute right-3 pointer-events-none text-text-muted">
            <Icons.Calendar className="w-4 h-4" />
          </div>
        </div>
        {error ? (
          <p className="text-[12px] leading-[16px] text-danger" role="alert">
            {error}
          </p>
        ) : helperText ? (
          <p className="text-[12px] leading-[16px] text-text-secondary">
            {helperText}
          </p>
        ) : null}
      </div>
    );
  }
);
DatePicker.displayName = 'DatePicker';


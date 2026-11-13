import React, { useId } from 'react';
import { cn } from '../lib/utils';
import { Icons } from './Icons';

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  options: SelectOption[];
  helperText?: string;
  error?: string;
}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, label, options, helperText, error, id, ...props }, ref) => {
    const generatedId = useId();
    const selectId = id || generatedId;
    const helperId = `${selectId}-helper`;
    const errorId = `${selectId}-error`;

    return (
      <div className="w-full flex flex-col gap-1.5 text-left">
        {label && (
          <label htmlFor={selectId} className="text-[13px] leading-[18px] font-medium text-text">
            {label}
            {props.required && <span className="text-danger ml-0.5">*</span>}
          </label>
        )}
        <div className="relative flex items-center">
          <select
            id={selectId}
            ref={ref}
            aria-invalid={Boolean(error)}
            aria-describedby={error ? errorId : helperText ? helperId : undefined}
            className={cn(
              'w-full min-h-[44px] px-3 py-2 pr-10 text-[14px] leading-[20px] text-text bg-white border rounded-[6px] appearance-none transition-colors cursor-pointer',
              error ? 'border-danger focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger' : 'border-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
              'disabled:bg-bg disabled:text-text-muted disabled:cursor-not-allowed',
              className
            )}
            {...props}
          >
            {options.map((opt) => (
              <option key={opt.value} value={opt.value} disabled={opt.disabled}>
                {opt.label}
              </option>
            ))}
          </select>
          <div className="absolute right-3 pointer-events-none text-text-muted">
            <Icons.ChevronDown className="w-4 h-4" />
          </div>
        </div>
        {error ? (
          <p id={errorId} className="text-[12px] leading-[16px] text-danger" role="alert">
            {error}
          </p>
        ) : helperText ? (
          <p id={helperId} className="text-[12px] leading-[16px] text-text-secondary">
            {helperText}
          </p>
        ) : null}
      </div>
    );
  }
);
Select.displayName = 'Select';


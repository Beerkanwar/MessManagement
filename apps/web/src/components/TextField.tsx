import React, { useId } from 'react';
import { cn } from '../lib/utils';

export interface TextFieldProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  helperText?: string;
  error?: string;
  startIcon?: React.ReactNode;
  endIcon?: React.ReactNode;
}

export const TextField = React.forwardRef<HTMLInputElement, TextFieldProps>(
  ({ className, label, helperText, error, id, startIcon, endIcon, ...props }, ref) => {
    const generatedId = useId();
    const inputId = id || generatedId;
    const helperId = `${inputId}-helper`;
    const errorId = `${inputId}-error`;

    return (
      <div className="w-full flex flex-col gap-1.5 text-left">
        {label && (
          <label htmlFor={inputId} className="text-[13px] leading-[18px] font-medium text-text">
            {label}
            {props.required && <span className="text-danger ml-0.5">*</span>}
          </label>
        )}
        <div className="relative flex items-center">
          {startIcon && <div className="absolute left-3 text-text-muted pointer-events-none flex items-center">{startIcon}</div>}
          <input
            id={inputId}
            ref={ref}
            aria-invalid={Boolean(error)}
            aria-describedby={error ? errorId : helperText ? helperId : undefined}
            className={cn(
              'w-full min-h-[44px] px-3 py-2 text-[14px] leading-[20px] text-text bg-white border rounded-[6px] transition-colors',
              'placeholder:text-text-muted',
              error ? 'border-danger focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger' : 'border-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
              'disabled:bg-bg disabled:text-text-muted disabled:cursor-not-allowed',
              startIcon ? 'pl-10' : '',
              endIcon ? 'pr-10' : '',
              className
            )}
            {...props}
          />
          {endIcon && <div className="absolute right-3 text-text-muted flex items-center">{endIcon}</div>}
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
TextField.displayName = 'TextField';


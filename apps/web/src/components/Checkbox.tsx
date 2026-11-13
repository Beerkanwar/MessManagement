import React, { useId } from 'react';
import { cn } from '../lib/utils';
import { Icons } from './Icons';

export interface CheckboxProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label?: string;
  helperText?: string;
}

export const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className, label, helperText, id, checked, ...props }, ref) => {
    const generatedId = useId();
    const checkboxId = id || generatedId;

    return (
      <div className="flex items-start gap-2.5 cursor-pointer">
        <div className="relative flex items-center justify-center pt-0.5">
          <input
            id={checkboxId}
            ref={ref}
            type="checkbox"
            checked={checked}
            className="peer sr-only"
            {...props}
          />
          <div
            className={cn(
              'w-5 h-5 rounded-[4px] border border-border bg-white transition-colors duration-150 flex items-center justify-center',
              'peer-checked:bg-primary peer-checked:border-primary',
              'peer-focus-visible:ring-2 peer-focus-visible:ring-primary peer-focus-visible:ring-offset-2',
              'peer-disabled:bg-bg peer-disabled:opacity-50 peer-disabled:cursor-not-allowed',
              className
            )}
          >
            {checked && <Icons.Check className="w-3.5 h-3.5 text-white stroke-[2.5]" />}
          </div>
        </div>
        {(label || helperText) && (
          <label htmlFor={checkboxId} className="flex flex-col select-none cursor-pointer">
            {label && <span className="text-[14px] leading-[20px] text-text font-normal">{label}</span>}
            {helperText && <span className="text-[12px] leading-[16px] text-text-secondary">{helperText}</span>}
          </label>
        )}
      </div>
    );
  }
);
Checkbox.displayName = 'Checkbox';


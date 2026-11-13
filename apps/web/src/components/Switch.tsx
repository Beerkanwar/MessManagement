import React, { useId } from 'react';
import { cn } from '../lib/utils';

export interface SwitchProps {
  label?: string;
  helperText?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  id?: string;
}

export const Switch: React.FC<SwitchProps> = ({
  label,
  helperText,
  checked,
  onChange,
  disabled = false,
  id,
}) => {
  const generatedId = useId();
  const switchId = id || generatedId;

  return (
    <div className="flex items-start gap-3">
      <button
        id={switchId}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => !disabled && onChange(!checked)}
        className={cn(
          'relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-175 ease-out',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          checked ? 'bg-primary' : 'bg-border-strong'
        )}
      >
        <span
          className={cn(
            'pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow-sm ring-0 transition-transform duration-175 ease-out',
            checked ? 'translate-x-5' : 'translate-x-0'
          )}
        />
      </button>
      {(label || helperText) && (
        <div className="flex flex-col select-none cursor-pointer" onClick={() => !disabled && onChange(!checked)}>
          {label && <span className="text-[14px] leading-[20px] text-text font-medium">{label}</span>}
          {helperText && <span className="text-[12px] leading-[16px] text-text-secondary">{helperText}</span>}
        </div>
      )}
    </div>
  );
};


import React from 'react';
import { Icons } from './Icons';

export interface QuantityStepperProps {
  label?: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (val: number) => void;
  disabled?: boolean;
}

export const QuantityStepper: React.FC<QuantityStepperProps> = ({
  label,
  value,
  min = 1,
  max = 99,
  step = 1,
  onChange,
  disabled = false,
}) => {
  const handleDecrement = () => {
    if (value - step >= min) {
      onChange(value - step);
    }
  };

  const handleIncrement = () => {
    if (value + step <= max) {
      onChange(value + step);
    }
  };

  return (
    <div className="flex flex-col gap-1.5 text-left">
      {label && <span className="text-[13px] leading-[18px] font-medium text-text">{label}</span>}
      <div className="inline-flex items-center border border-border rounded-[6px] bg-white h-[44px] overflow-hidden select-none">
        <button
          type="button"
          onClick={handleDecrement}
          disabled={disabled || value <= min}
          aria-label="Decrease quantity"
          className="min-w-[44px] h-full flex items-center justify-center text-text hover:bg-bg active:bg-[#E2E8F0] disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-inset"
        >
          <Icons.Minus className="w-4 h-4" />
        </button>
        <span
          className="w-12 text-center text-[15px] font-semibold text-text tabular-nums select-none"
          aria-live="polite"
        >
          {value}
        </span>
        <button
          type="button"
          onClick={handleIncrement}
          disabled={disabled || value >= max}
          aria-label="Increase quantity"
          className="min-w-[44px] h-full flex items-center justify-center text-text hover:bg-bg active:bg-[#E2E8F0] disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-inset"
        >
          <Icons.Plus className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};


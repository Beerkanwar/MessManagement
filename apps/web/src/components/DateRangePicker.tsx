import React from 'react';
import { DatePicker } from './DatePicker';

export interface DateRangePickerProps {
  label?: string;
  startDate?: string;
  endDate?: string;
  onStartDateChange?: (val: string) => void;
  onEndDateChange?: (val: string) => void;
  error?: string;
  helperText?: string;
}

export const DateRangePicker: React.FC<DateRangePickerProps> = ({
  label,
  startDate,
  endDate,
  onStartDateChange,
  onEndDateChange,
  error,
  helperText,
}) => {
  return (
    <div className="flex flex-col gap-1.5 text-left">
      {label && (
        <span className="text-[13px] leading-[18px] font-medium text-text">
          {label}
        </span>
      )}
      <div className="flex items-center gap-2">
        <DatePicker
          aria-label="Start Date"
          value={startDate}
          onChange={(e) => onStartDateChange?.(e.target.value)}
        />
        <span className="text-text-muted text-[14px]">to</span>
        <DatePicker
          aria-label="End Date"
          value={endDate}
          onChange={(e) => onEndDateChange?.(e.target.value)}
        />
      </div>
      {error ? (
        <p className="text-[12px] leading-[16px] text-danger" role="alert">{error}</p>
      ) : helperText ? (
        <p className="text-[12px] leading-[16px] text-text-secondary">{helperText}</p>
      ) : null}
    </div>
  );
};


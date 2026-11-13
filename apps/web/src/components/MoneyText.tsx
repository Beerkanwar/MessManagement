import React from 'react';
import { cn } from '../lib/utils';

export interface MoneyTextProps {
  amountInRupees: number;
  className?: string;
}

/**
 * Formats monetary amounts according to project conventions:
 * - Rupee symbol (₹)
 * - Indian digit grouping (en-IN)
 * - Two decimal places
 * - Tabular figures
 * - Negative balances in danger color with a minus sign, never parentheses
 */
export const MoneyText: React.FC<MoneyTextProps> = ({ amountInRupees, className }) => {
  const isNegative = amountInRupees < 0;
  const absAmount = Math.abs(amountInRupees);

  const formatted = new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(absAmount);

  return (
    <span
      className={cn(
        'tabular-nums font-medium inline-flex items-baseline',
        isNegative ? 'text-danger font-semibold' : 'text-text',
        className
      )}
    >
      {isNegative && '-'}₹{formatted}
    </span>
  );
};


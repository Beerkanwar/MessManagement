import React from 'react';
import { cn } from '../lib/utils';

export interface DateTextProps {
  date: string | Date;
  includeTime?: boolean;
  className?: string;
}

const MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

/**
 * Formats dates according to project conventions:
 * - Date only: "21 Aug 2026"
 * - Date-time: "21 Aug, 11:42 AM" (with tooltip indicating IST)
 */
export const DateText: React.FC<DateTextProps> = ({ date, includeTime = false, className }) => {
  const d = typeof date === 'string' ? new Date(date) : date;
  if (isNaN(d.getTime())) {
    return <span className={className}>Invalid date</span>;
  }

  // Formatting strictly in Indian Standard Time (IST: UTC+5:30)
  const utc = d.getTime() + d.getTimezoneOffset() * 60000;
  const istOffsetMs = 5.5 * 3600000;
  const istDate = new Date(utc + istOffsetMs);

  const day = istDate.getDate();
  const month = MONTHS[istDate.getMonth()];
  const year = istDate.getFullYear();

  let formatted = `${day} ${month} ${year}`;

  if (includeTime) {
    let hours = istDate.getHours();
    const minutes = istDate.getMinutes().toString().padStart(2, '0');
    const ampm = hours >= 12 ? 'PM' : 'AM';
    hours = hours % 12 || 12;
    formatted = `${day} ${month}, ${hours}:${minutes} ${ampm}`;
  }

  return (
    <span
      title={includeTime ? 'Time displayed in Indian Standard Time (IST)' : undefined}
      className={cn('tabular-nums text-text', className)}
    >
      {formatted}
    </span>
  );
};


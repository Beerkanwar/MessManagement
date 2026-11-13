import React from 'react';
import { cn } from '../lib/utils';

export interface QrDisplayProps {
  payload: string;
  code: string;
  remainingSeconds: number;
  totalSeconds?: number;
  rollNumber?: string;
  className?: string;
}

export const QrDisplay: React.FC<QrDisplayProps> = ({
  payload,
  code,
  remainingSeconds,
  totalSeconds = 30,
  rollNumber,
  className,
}) => {
  const fraction = Math.max(0, Math.min(1, remainingSeconds / totalSeconds));
  const radius = 28;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - fraction * circumference;

  // Format code as "123 456" for glanceability
  const formattedCode =
    code.length === 6 ? `${code.slice(0, 3)} ${code.slice(3)}` : code;

  return (
    <div
      className={cn(
        'flex flex-col items-center bg-surface border border-border rounded-[16px] p-6 shadow-sm select-none max-w-xs mx-auto',
        className
      )}
    >
      {/* Student / Roll Header */}
      {rollNumber && (
        <div className="mb-4 text-center">
          <span className="block text-[11px] font-bold text-text-muted uppercase tracking-wider">
            Student Identity
          </span>
          <span className="text-[17px] font-bold text-text tabular-nums">{rollNumber}</span>
        </div>
      )}

      {/* QR Code Container */}
      <div className="relative p-4 bg-white border-2 border-border rounded-[12px] shadow-inner mb-5">
        <svg
          viewBox="0 0 100 100"
          className="w-48 h-48 text-text"
          fill="currentColor"
          aria-label={`QR payload: ${payload}`}
        >
          {/* Stylized reproducible QR pattern representing the dynamic HMAC token */}
          <rect x="0" y="0" width="30" height="30" fill="none" stroke="currentColor" strokeWidth="6" />
          <rect x="7" y="7" width="16" height="16" />
          <rect x="70" y="0" width="30" height="30" fill="none" stroke="currentColor" strokeWidth="6" />
          <rect x="77" y="7" width="16" height="16" />
          <rect x="0" y="70" width="30" height="30" fill="none" stroke="currentColor" strokeWidth="6" />
          <rect x="7" y="77" width="16" height="16" />
          {/* Center and data bits */}
          <rect x="42" y="10" width="8" height="8" />
          <rect x="52" y="22" width="8" height="8" />
          <rect x="10" y="42" width="8" height="8" />
          <rect x="22" y="52" width="8" height="8" />
          <rect x="40" y="40" width="20" height="20" rx="3" />
          <rect x="70" y="45" width="10" height="10" />
          <rect x="45" y="70" width="10" height="10" />
          <rect x="75" y="75" width="15" height="15" />
        </svg>
      </div>

      {/* Code and Countdown Ring */}
      <div className="flex items-center justify-between w-full px-2">
        <div className="text-left">
          <span className="block text-[11px] font-medium text-text-muted uppercase">Verification Code</span>
          <span className="text-[24px] font-bold tracking-wider text-text font-mono tabular-nums">
            {formattedCode}
          </span>
        </div>

        {/* 30-second Countdown Ring */}
        <div className="relative w-16 h-16 flex items-center justify-center">
          <svg className="w-16 h-16 transform -rotate-90">
            <circle
              cx="32"
              cy="32"
              r={radius}
              stroke="#E2E8F0"
              strokeWidth="4"
              fill="transparent"
            />
            <circle
              cx="32"
              cy="32"
              r={radius}
              stroke={fraction > 0.2 ? '#0F766E' : '#B91C1C'}
              strokeWidth="4"
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
              strokeLinecap="round"
              fill="transparent"
              className="transition-all duration-300 ease-linear"
            />
          </svg>
          <span className="absolute text-[13px] font-bold tabular-nums text-text">
            {remainingSeconds}s
          </span>
        </div>
      </div>
    </div>
  );
};


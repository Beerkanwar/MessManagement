import React from 'react';
import { cn } from '../lib/utils';
import { statusMapping, statusColorStyles, StatusColorType } from '../design/tokens';
import { Icons } from './Icons';

export type StatusDomain = keyof typeof statusMapping;

export interface StatusBadgeProps {
  domain?: StatusDomain;
  status: string;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ domain, status, className }) => {
  let colorType: StatusColorType = 'neutral';

  if (domain && statusMapping[domain]) {
    const domainMap = statusMapping[domain] as Record<string, string>;
    if (domainMap[status]) {
      colorType = domainMap[status] as StatusColorType;
    }
  } else {
    // If domain is omitted, scan known domains
    for (const d of Object.values(statusMapping)) {
      const mapping = d as Record<string, string>;
      if (mapping[status]) {
        colorType = mapping[status] as StatusColorType;
        break;
      }
    }
  }

  const style = statusColorStyles[colorType] || statusColorStyles.neutral;

  // Render accompanying accessible icon (Principle 2: State is never color alone)
  const renderIcon = () => {
    switch (colorType) {
      case 'success':
        return <Icons.CheckCircle className="w-3.5 h-3.5 stroke-[2]" />;
      case 'warning':
        return <Icons.AlertTriangle className="w-3.5 h-3.5 stroke-[2]" />;
      case 'danger':
        return <Icons.XCircle className="w-3.5 h-3.5 stroke-[2]" />;
      case 'info':
        return <Icons.Info className="w-3.5 h-3.5 stroke-[2]" />;
      case 'neutral':
      default:
        return <span className="w-1.5 h-1.5 rounded-full bg-current opacity-70" />;
    }
  };

  const formattedLabel = status.replace(/_/g, ' ');

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-[9999px] text-[12px] leading-[16px] font-semibold border select-none',
        className
      )}
      style={{
        backgroundColor: style.bg,
        color: style.text,
        borderColor: style.border,
      }}
    >
      {renderIcon()}
      <span>{formattedLabel}</span>
    </span>
  );
};


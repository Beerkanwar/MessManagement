import React from 'react';
import { cn } from '../lib/utils';
import { scannerResults } from '../design/tokens';
import { Icons } from './Icons';

export type ScanResultType = keyof typeof scannerResults;

export interface ScanResultOverlayProps {
  resultType: ScanResultType;
  studentName?: string;
  rollNumber?: string;
  mealType?: string;
  detailNote?: string;
  onDismiss?: () => void;
  className?: string;
}

export const ScanResultOverlay: React.FC<ScanResultOverlayProps> = ({
  resultType,
  studentName,
  rollNumber,
  mealType,
  detailNote,
  onDismiss,
  className,
}) => {
  const config = scannerResults[resultType] || scannerResults.SUCCESS;

  const renderIcon = () => {
    switch (resultType) {
      case 'SUCCESS':
      case 'SUCCESS_PAUSE_NOTICE':
        return <Icons.CheckCircle className="w-24 h-24 stroke-[2.5]" />;
      case 'DUPLICATE':
        return <Icons.AlertTriangle className="w-24 h-24 stroke-[2.5]" />;
      case 'INVALID_CODE':
      case 'UNKNOWN_ROLL':
        return <Icons.XCircle className="w-24 h-24 stroke-[2.5]" />;
      case 'TIME_INVALID':
      default:
        return <Icons.Clock className="w-24 h-24 stroke-[2.5]" />;
    }
  };

  return (
    <div
      role="region"
      aria-live="assertive"
      onClick={onDismiss}
      className={cn(
        'fixed inset-0 z-50 flex flex-col items-center justify-center p-8 text-center text-white select-none cursor-pointer',
        className
      )}
      style={{ backgroundColor: config.bg }}
    >
      <div className="animate-in zoom-in-75 duration-150 flex flex-col items-center max-w-xl mx-auto">
        {/* Large Accessible State Icon */}
        <div className="mb-6 drop-shadow-md">{renderIcon()}</div>

        {/* State Label Word (Never color alone) */}
        <h1 className="text-[32px] md:text-[40px] font-black uppercase tracking-wider mb-2">
          {config.label}
        </h1>

        {/* Scan Details */}
        {(studentName || rollNumber) && (
          <div className="mt-4 p-4 rounded-[12px] bg-black/15 backdrop-blur-sm border border-white/20 w-full text-center">
            {studentName && (
              <h2 className="text-[24px] md:text-[30px] font-bold tracking-tight">
                {studentName}
              </h2>
            )}
            {rollNumber && (
              <p className="text-[18px] md:text-[22px] font-mono font-semibold tracking-wider mt-1 opacity-90 tabular-nums">
                {rollNumber}
              </p>
            )}
            {mealType && (
              <p className="text-[14px] uppercase tracking-widest font-semibold mt-2 opacity-80">
                {mealType}
              </p>
            )}
          </div>
        )}

        {detailNote && (
          <p className="mt-6 text-[16px] md:text-[18px] font-medium bg-black/20 px-4 py-2 rounded-full border border-white/20">
            {detailNote}
          </p>
        )}

        <span className="mt-12 text-[13px] opacity-75 font-medium tracking-wide">
          Tap anywhere or scan next student
        </span>
      </div>
    </div>
  );
};


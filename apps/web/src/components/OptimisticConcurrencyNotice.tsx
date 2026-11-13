import React from 'react';
import { Button } from './Button';
import { Icons } from './Icons';

export interface OptimisticConcurrencyNoticeProps {
  isOpen: boolean;
  onReload: () => void;
  onCancel?: () => void;
}

export const OptimisticConcurrencyNotice: React.FC<OptimisticConcurrencyNoticeProps> = ({
  isOpen,
  onReload,
  onCancel,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="fixed inset-0 bg-[#0F172A]/40 backdrop-blur-[1px]" aria-hidden="true" />
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="concurrency-title"
        aria-describedby="concurrency-desc"
        className="relative w-full max-w-md bg-surface border border-warning/40 rounded-[16px] shadow-dialog p-6 z-10 text-center select-none animate-in zoom-in-95 duration-150"
      >
        <div className="w-12 h-12 rounded-full bg-warning-subtle text-warning flex items-center justify-center mx-auto mb-3">
          <Icons.AlertTriangle className="w-6 h-6 stroke-[2]" />
        </div>

        <h3 id="concurrency-title" className="text-[17px] font-bold text-text mb-1">
          Record Changed by Someone Else
        </h3>
        <p id="concurrency-desc" className="text-[13px] leading-[18px] text-text-secondary mb-6">
          This record was modified since you loaded it. To prevent overwriting another administrator's updates, please reload the latest data.
        </p>

        <div className="flex items-center justify-center gap-3">
          {onCancel && (
            <Button variant="secondary" onClick={onCancel}>
              Review Draft
            </Button>
          )}
          <Button variant="primary" onClick={onReload} icon={<Icons.RefreshCw className="w-4 h-4" />}>
            Reload latest version
          </Button>
        </div>
      </div>
    </div>
  );
};


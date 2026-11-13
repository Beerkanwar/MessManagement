import React, { useState, useEffect } from 'react';
import { cn } from '../lib/utils';
import { Button } from './Button';
import { Icons } from './Icons';

export interface ReasonDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (reason: string) => void;
  title: string;
  description: string;
  placeholder?: string;
  minLength?: number;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'danger' | 'primary';
  loading?: boolean;
}

export const ReasonDialog: React.FC<ReasonDialogProps> = ({
  isOpen,
  onClose,
  onConfirm,
  title,
  description,
  placeholder = 'Explain the operational or audit reason for this action...',
  minLength = 10,
  confirmLabel = 'Submit Reason',
  cancelLabel = 'Cancel',
  variant = 'primary',
  loading = false,
}) => {
  const [reason, setReason] = useState('');
  const [touched, setTouched] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setReason('');
      setTouched(false);
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const trimmed = reason.trim();
  const isValid = trimmed.length >= minLength;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isValid && !loading) {
      onConfirm(trimmed);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-[#0F172A]/40 backdrop-blur-[1px] transition-opacity"
        onClick={() => !loading && onClose()}
        aria-hidden="true"
      />

      {/* Dialog box */}
      <form
        onSubmit={handleSubmit}
        role="dialog"
        aria-modal="true"
        aria-labelledby="reason-dialog-title"
        className="relative w-full max-w-lg bg-surface border border-border rounded-[16px] shadow-dialog p-6 z-10 select-none animate-in fade-in zoom-in-95 duration-150"
      >
        <div className="flex items-start gap-4 mb-4">
          <div
            className={cn(
              'w-10 h-10 rounded-full flex items-center justify-center shrink-0',
              variant === 'danger' ? 'bg-danger-subtle text-danger' : 'bg-primary-subtle text-primary'
            )}
          >
            {variant === 'danger' ? (
              <Icons.AlertTriangle className="w-5 h-5 stroke-[2]" />
            ) : (
              <Icons.Info className="w-5 h-5 stroke-[2]" />
            )}
          </div>
          <div>
            <h3 id="reason-dialog-title" className="text-[17px] font-semibold text-text">
              {title}
            </h3>
            <p className="text-[14px] leading-[20px] text-text-secondary mt-1">
              {description}
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-1.5 text-left mb-6">
          <label htmlFor="reason-input" className="text-[13px] font-medium text-text">
            Mandatory Reason <span className="text-danger">*</span>
          </label>
          <textarea
            id="reason-input"
            rows={3}
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
              setTouched(true);
            }}
            placeholder={placeholder}
            className={cn(
              'w-full p-3 text-[14px] leading-[20px] text-text bg-white border rounded-[6px] transition-colors resize-y',
              touched && !isValid ? 'border-danger focus-visible:ring-danger' : 'border-border focus-visible:ring-primary',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1'
            )}
            required
          />
          <div className="flex items-center justify-between text-[12px]">
            <span className={touched && !isValid ? 'text-danger font-medium' : 'text-text-muted'}>
              {touched && !isValid
                ? `Minimum ${minLength} characters required (${trimmed.length}/${minLength})`
                : `Audited mandatory explanation`}
            </span>
            <span className="text-text-muted tabular-nums">
              {trimmed.length} / {minLength} min
            </span>
          </div>
        </div>

        <div className="flex items-center justify-end gap-3">
          <Button
            type="button"
            variant="secondary"
            onClick={onClose}
            disabled={loading}
          >
            {cancelLabel}
          </Button>
          <Button
            type="submit"
            variant={variant === 'danger' ? 'danger' : 'primary'}
            disabled={!isValid || loading}
            loading={loading}
          >
            {confirmLabel}
          </Button>
        </div>
      </form>
    </div>
  );
};


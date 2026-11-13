import React, { useState } from 'react';
import { cn } from '../lib/utils';
import { Icons } from './Icons';

export interface ErrorStateProps {
  errorCode: string;
  message: string;
  traceId?: string;
  onRetry?: () => void;
  className?: string;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  errorCode,
  message,
  traceId,
  onRetry,
  className,
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopyTraceId = () => {
    if (traceId) {
      navigator.clipboard?.writeText(traceId);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div
      role="alert"
      className={cn(
        'flex flex-col items-center justify-center p-8 text-center max-w-md mx-auto bg-surface border border-danger/30 rounded-[10px] shadow-sm',
        className
      )}
    >
      <div className="w-12 h-12 rounded-full bg-danger-subtle flex items-center justify-center text-danger mb-4">
        <Icons.XCircle className="w-6 h-6 stroke-[2]" />
      </div>

      <span className="inline-block px-2.5 py-0.5 mb-2 text-[11px] font-bold tracking-wider text-danger uppercase bg-danger-subtle rounded border border-danger/20 font-mono">
        {errorCode}
      </span>

      <h3 className="text-[17px] leading-[24px] font-semibold text-text mb-1">
        Something went wrong
      </h3>
      <p className="text-[13px] leading-[18px] text-text-secondary mb-4">{message}</p>

      {traceId && (
        <div className="w-full bg-bg border border-border rounded-[6px] p-2.5 mb-4 flex items-center justify-between gap-2 text-left">
          <div className="overflow-hidden">
            <span className="block text-[11px] font-medium text-text-muted uppercase">Trace ID</span>
            <code className="text-[12px] font-mono text-text block truncate select-all">{traceId}</code>
          </div>
          <button
            type="button"
            onClick={handleCopyTraceId}
            title="Copy Trace ID"
            aria-label="Copy Trace ID"
            className="p-1.5 rounded hover:bg-white text-text-secondary hover:text-text border border-transparent hover:border-border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary shrink-0"
          >
            {copied ? (
              <Icons.Check className="w-4 h-4 text-success stroke-[2.5]" />
            ) : (
              <Icons.Copy className="w-4 h-4" />
            )}
          </button>
        </div>
      )}

      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-2 px-4 py-2 text-[13px] font-medium text-white bg-primary hover:bg-primary-hover rounded-[6px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
        >
          <Icons.RefreshCw className="w-4 h-4" />
          <span>Try again</span>
        </button>
      )}
    </div>
  );
};


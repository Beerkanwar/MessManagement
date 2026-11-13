import React, { useId } from 'react';
import { cn } from '../lib/utils';

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  helperText?: string;
  error?: string;
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, label, helperText, error, id, ...props }, ref) => {
    const generatedId = useId();
    const textareaId = id || generatedId;

    return (
      <div className="w-full flex flex-col gap-1.5 text-left">
        {label && (
          <label htmlFor={textareaId} className="text-[13px] leading-[18px] font-medium text-text">
            {label}
            {props.required && <span className="text-danger ml-0.5">*</span>}
          </label>
        )}
        <textarea
          id={textareaId}
          ref={ref}
          aria-invalid={Boolean(error)}
          className={cn(
            'w-full min-h-[96px] p-3 text-[14px] leading-[20px] text-text bg-white border rounded-[6px] transition-colors resize-y',
            error ? 'border-danger focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger' : 'border-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
            'disabled:bg-bg disabled:text-text-muted disabled:cursor-not-allowed',
            className
          )}
          {...props}
        />
        {error ? (
          <p className="text-[12px] leading-[16px] text-danger" role="alert">{error}</p>
        ) : helperText ? (
          <p className="text-[12px] leading-[16px] text-text-secondary">{helperText}</p>
        ) : null}
      </div>
    );
  }
);
Textarea.displayName = 'Textarea';


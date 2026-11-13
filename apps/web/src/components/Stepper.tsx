import React from 'react';
import { cn } from '../lib/utils';
import { Icons } from './Icons';

export interface StepItem {
  id: string | number;
  label: string;
  description?: string;
}

export interface StepperProps {
  steps: StepItem[];
  currentStep: number; // 0-indexed
  onStepClick?: (stepIndex: number) => void;
  className?: string;
}

export const Stepper: React.FC<StepperProps> = ({
  steps,
  currentStep,
  onStepClick,
  className,
}) => {
  return (
    <nav aria-label="Progress" className={cn('w-full', className)}>
      <ol className="flex items-center w-full">
        {steps.map((step, index) => {
          const isCompleted = index < currentStep;
          const isCurrent = index === currentStep;
          const isClickable = Boolean(onStepClick && index <= currentStep);

          return (
            <li
              key={step.id}
              className={cn(
                'relative flex-1 flex items-center',
                index === steps.length - 1 ? 'flex-none' : ''
              )}
            >
              <div
                onClick={() => isClickable && onStepClick?.(index)}
                className={cn(
                  'flex items-center gap-3 group',
                  isClickable ? 'cursor-pointer' : 'cursor-default'
                )}
              >
                <div
                  className={cn(
                    'w-9 h-9 rounded-full flex items-center justify-center font-semibold text-[14px] transition-colors',
                    isCompleted && 'bg-success text-white',
                    isCurrent && 'bg-primary text-white ring-4 ring-primary-subtle',
                    !isCompleted && !isCurrent && 'bg-bg text-text-muted border border-border'
                  )}
                  aria-current={isCurrent ? 'step' : undefined}
                >
                  {isCompleted ? (
                    <Icons.Check className="w-5 h-5 stroke-[2.5]" />
                  ) : (
                    <span>{index + 1}</span>
                  )}
                </div>
                <div className="hidden sm:block text-left">
                  <span
                    className={cn(
                      'block text-[13px] font-medium leading-none',
                      isCurrent ? 'text-primary font-semibold' : isCompleted ? 'text-text' : 'text-text-muted'
                    )}
                  >
                    {step.label}
                  </span>
                  {step.description && (
                    <span className="block text-[11px] text-text-muted mt-0.5">
                      {step.description}
                    </span>
                  )}
                </div>
              </div>

              {index < steps.length - 1 && (
                <div
                  className={cn(
                    'flex-1 h-0.5 mx-4 transition-colors',
                    index < currentStep ? 'bg-success' : 'bg-border'
                  )}
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
};


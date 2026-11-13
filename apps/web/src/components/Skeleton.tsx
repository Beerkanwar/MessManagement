import React from 'react';
import { cn } from '../lib/utils';

export interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'text' | 'circular' | 'rectangular';
  width?: string | number;
  height?: string | number;
}

export const Skeleton: React.FC<SkeletonProps> = ({
  className,
  variant = 'rectangular',
  width,
  height,
  style,
  ...props
}) => {
  const variantStyles = {
    text: 'rounded-[4px] h-4 w-full',
    circular: 'rounded-full',
    rectangular: 'rounded-[6px]',
  };

  return (
    <div
      aria-hidden="true"
      className={cn('animate-pulse bg-border-strong/60', variantStyles[variant], className)}
      style={{
        width,
        height,
        ...style,
      }}
      {...props}
    />
  );
};


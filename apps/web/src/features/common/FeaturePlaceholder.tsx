import React from 'react';
import { Card } from '../../components/Card';
import { Icons } from '../../components/Icons';

export interface FeaturePlaceholderProps {
  title: string;
  description: string;
  phaseTarget: string;
}

export const FeaturePlaceholder: React.FC<FeaturePlaceholderProps> = ({
  title,
  description,
  phaseTarget,
}) => {
  return (
    <div className="space-y-6 select-none">
      <div className="border-b border-border pb-4">
        <h2 className="text-[22px] font-bold text-text">{title}</h2>
        <p className="text-[13px] text-text-secondary mt-0.5">{description}</p>
      </div>

      <Card>
        <div className="flex flex-col items-center justify-center p-12 text-center">
          <div className="w-12 h-12 rounded-full bg-primary-subtle text-primary flex items-center justify-center mb-4">
            <Icons.Calendar className="w-6 h-6 stroke-[1.5]" />
          </div>
          <span className="text-[11px] font-bold text-primary uppercase tracking-widest bg-primary-subtle px-2.5 py-0.5 rounded border border-primary-border mb-2">
            Target: {phaseTarget}
          </span>
          <h3 className="text-[17px] font-bold text-text mb-1">{title} Foundation Ready</h3>
          <p className="text-[13px] text-text-secondary max-w-md">
            This route is scoped and protected under Phase 15 web foundation. Full functional screens will be connected in {phaseTarget}.
          </p>
        </div>
      </Card>
    </div>
  );
};


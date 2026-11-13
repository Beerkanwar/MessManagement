import React from 'react';
import { Button } from './Button';
import { Icons } from './Icons';

export interface WrongClientNoticeProps {
  onBackToLogin: () => void;
}

export const WrongClientNotice: React.FC<WrongClientNoticeProps> = ({ onBackToLogin }) => {
  return (
    <div className="min-h-screen bg-bg flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-surface border border-border rounded-[16px] shadow-sm p-8 text-center select-none">
        <div className="w-16 h-16 rounded-full bg-primary-subtle text-primary flex items-center justify-center mx-auto mb-4">
          <Icons.QrCode className="w-8 h-8 stroke-[1.75]" />
        </div>

        <span className="text-[12px] font-bold text-primary tracking-widest uppercase bg-primary-subtle px-2.5 py-1 rounded border border-primary-border inline-block mb-3">
          Mobile App Required
        </span>

        <h2 className="text-[22px] font-bold text-text mb-2">
          Use the Mobile App
        </h2>
        <p className="text-[14px] leading-[22px] text-text-secondary mb-6">
          Students and Mess Managers access the system via the dedicated mobile application for dynamic QR codes, offline attendance recording, and instant diet meal scanning.
        </p>

        <div className="p-4 bg-bg rounded-[10px] border border-border text-left mb-6 space-y-2">
          <div className="flex items-center gap-2 text-[13px] text-text">
            <Icons.Check className="w-4 h-4 text-success" />
            <span>Dynamic rotating QR verification code</span>
          </div>
          <div className="flex items-center gap-2 text-[13px] text-text">
            <Icons.Check className="w-4 h-4 text-success" />
            <span>Diet pause requests & daily menu inspection</span>
          </div>
          <div className="flex items-center gap-2 text-[13px] text-text">
            <Icons.Check className="w-4 h-4 text-success" />
            <span>Fast, reliable offline attendance sync</span>
          </div>
        </div>

        <Button
          variant="secondary"
          onClick={onBackToLogin}
          className="w-full justify-center"
        >
          Return to Sign In
        </Button>
      </div>
    </div>
  );
};


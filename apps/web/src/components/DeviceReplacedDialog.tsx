import React from 'react';
import { Button } from './Button';
import { Icons } from './Icons';

export interface DeviceReplacedDialogProps {
  isOpen: boolean;
  onSignInAgain: () => void;
}

export const DeviceReplacedDialog: React.FC<DeviceReplacedDialogProps> = ({
  isOpen,
  onSignInAgain,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Non-dismissible backdrop */}
      <div className="fixed inset-0 bg-[#0F172A]/60 backdrop-blur-[2px]" aria-hidden="true" />

      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="device-dialog-title"
        className="relative w-full max-w-md bg-surface border border-border rounded-[16px] shadow-2xl p-6 z-10 text-center animate-in zoom-in-95 duration-150 select-none"
      >
        <div className="w-12 h-12 rounded-full bg-warning-subtle text-warning flex items-center justify-center mx-auto mb-4">
          <Icons.AlertTriangle className="w-6 h-6 stroke-[2]" />
        </div>

        <h3 id="device-dialog-title" className="text-[18px] font-bold text-text mb-2">
          You signed in on another device
        </h3>
        <p className="text-[14px] leading-[20px] text-text-secondary mb-6">
          Each account has exactly one active session. To continue using the web application from this browser, please sign in again to re-bind this device.
        </p>

        <Button
          variant="primary"
          onClick={onSignInAgain}
          className="w-full justify-center min-h-[48px]"
        >
          Sign in again
        </Button>
      </div>
    </div>
  );
};


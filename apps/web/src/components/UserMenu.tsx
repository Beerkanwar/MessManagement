import React, { useState, useRef, useEffect } from 'react';
import { useAuth } from '../state/auth';
import { Icons } from './Icons';

export interface UserMenuProps {
  onChangePasswordClick: () => void;
}

export const UserMenu: React.FC<UserMenuProps> = ({ onChangePasswordClick }) => {
  const { user, role, assignment, logout } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const roleLabel =
    role === 'SUPER_ADMIN'
      ? 'Super Admin'
      : role === 'HOSTEL_CLERK'
      ? 'Hostel Clerk'
      : role;

  const scopeLabel =
    assignment?.hostel_name || (assignment?.hostel_id ? `Hostel ${assignment.hostel_id}` : null);

  return (
    <div className="relative select-none" ref={menuRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
        aria-haspopup="menu"
        className="flex items-center gap-3 p-1.5 rounded-[6px] hover:bg-bg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        <div className="w-8 h-8 rounded-full bg-primary text-white font-bold text-[13px] flex items-center justify-center">
          {user?.full_name ? user.full_name.charAt(0).toUpperCase() : 'U'}
        </div>
        <div className="hidden sm:block text-left leading-tight">
          <span className="block text-[13px] font-semibold text-text truncate max-w-[140px]">
            {user?.full_name || 'Staff User'}
          </span>
          <span className="block text-[11px] text-text-secondary">
            {roleLabel} {scopeLabel ? `• ${scopeLabel}` : ''}
          </span>
        </div>
        <Icons.ChevronDown className="w-4 h-4 text-text-muted" />
      </button>

      {isOpen && (
        <div
          role="menu"
          aria-label="User profile and options"
          className="absolute right-0 mt-2 w-64 bg-surface border border-border rounded-[8px] shadow-menu py-2 z-50 animate-in fade-in duration-100"
        >
          <div className="px-4 py-2 border-b border-border">
            <span className="block text-[13px] font-bold text-text truncate">
              {user?.full_name}
            </span>
            <span className="block text-[12px] text-text-secondary truncate mt-0.5">
              {user?.email}
            </span>
            <span className="inline-block mt-2 px-2 py-0.5 bg-primary-subtle text-primary border border-primary-border rounded text-[11px] font-semibold">
              {roleLabel}
            </span>
            {scopeLabel && (
              <span className="block text-[11px] text-text-muted mt-1 font-medium">
                Scope: {scopeLabel}
              </span>
            )}
          </div>

          <div className="py-1">
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setIsOpen(false);
                onChangePasswordClick();
              }}
              className="w-full text-left px-4 py-2 text-[13px] text-text hover:bg-bg transition-colors flex items-center gap-2"
            >
              <Icons.Lock className="w-4 h-4 text-text-secondary" />
              <span>Change Password</span>
            </button>
          </div>

          <div className="border-t border-border pt-1">
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setIsOpen(false);
                logout();
              }}
              className="w-full text-left px-4 py-2 text-[13px] text-danger hover:bg-danger-subtle transition-colors flex items-center gap-2 font-medium"
            >
              <Icons.XCircle className="w-4 h-4 text-danger" />
              <span>Sign out</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};


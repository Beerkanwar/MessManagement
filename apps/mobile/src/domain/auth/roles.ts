import { UserRole } from '../types';

export const MOBILE_ALLOWED_ROLES: readonly UserRole[] = ['STUDENT', 'MESS_MANAGER'] as const;
export const WEB_ONLY_ROLES: readonly UserRole[] = ['HOSTEL_CLERK', 'SUPER_ADMIN'] as const;

export function isMobileAllowedRole(role: string | null | undefined): role is 'STUDENT' | 'MESS_MANAGER' {
  if (!role) return false;
  return role === 'STUDENT' || role === 'MESS_MANAGER';
}

export function isWebOnlyRole(role: string | null | undefined): boolean {
  if (!role) return false;
  return role === 'HOSTEL_CLERK' || role === 'SUPER_ADMIN';
}

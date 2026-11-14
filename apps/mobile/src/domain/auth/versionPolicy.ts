import { VersionPolicy } from '../types';

export function isVersionBlocked(policy: VersionPolicy | null | undefined): boolean {
  if (!policy) return false;
  return policy.status === 'BLOCKED';
}

export function isVersionDeprecated(policy: VersionPolicy | null | undefined): boolean {
  if (!policy) return false;
  return policy.status === 'DEPRECATED';
}

export function isVersionSupported(policy: VersionPolicy | null | undefined): boolean {
  if (!policy) return true;
  return policy.status === 'SUPPORTED';
}

export function canAccessApp(policy: VersionPolicy | null | undefined): boolean {
  return !isVersionBlocked(policy);
}

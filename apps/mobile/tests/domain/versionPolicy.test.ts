// Test Checkpoint: Blocked and deprecated version policies behave as in DEC-18
// Domain tests run without any React Native runtime per SDD §6.1
import {
  isVersionBlocked,
  isVersionDeprecated,
  isVersionSupported,
  canAccessApp,
} from '../../src/domain/auth/versionPolicy';
import { VersionPolicy } from '../../src/domain/types';

describe('Domain: Version Policy (DEC-18)', () => {
  it('correctly identifies SUPPORTED version', () => {
    const policy: VersionPolicy = { status: 'SUPPORTED' };
    expect(isVersionSupported(policy)).toBe(true);
    expect(isVersionDeprecated(policy)).toBe(false);
    expect(isVersionBlocked(policy)).toBe(false);
    expect(canAccessApp(policy)).toBe(true);
  });

  it('correctly identifies DEPRECATED version allowing access with banner', () => {
    const policy: VersionPolicy = {
      status: 'DEPRECATED',
      force_update_message: 'Please update your application soon.',
    };
    expect(isVersionSupported(policy)).toBe(false);
    expect(isVersionDeprecated(policy)).toBe(true);
    expect(isVersionBlocked(policy)).toBe(false);
    expect(canAccessApp(policy)).toBe(true);
  });

  it('correctly identifies BLOCKED version refusing access', () => {
    const policy: VersionPolicy = {
      status: 'BLOCKED',
      force_update_message: 'This version is obsolete.',
    };
    expect(isVersionSupported(policy)).toBe(false);
    expect(isVersionDeprecated(policy)).toBe(false);
    expect(isVersionBlocked(policy)).toBe(true);
    expect(canAccessApp(policy)).toBe(false);
  });

  it('defaults gracefully when policy is null or undefined', () => {
    expect(isVersionSupported(null)).toBe(true);
    expect(isVersionBlocked(null)).toBe(false);
    expect(canAccessApp(null)).toBe(true);
  });
});

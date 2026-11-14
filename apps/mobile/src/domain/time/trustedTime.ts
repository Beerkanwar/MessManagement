import { TrustedTimeStatus } from '../types';

export const MAX_OFFLINE_WINDOW_MS = 72 * 60 * 60 * 1000; // 72 hours
export const EXPIRING_THRESHOLD_MS = 60 * 60 * 1000; // 1 hour remaining before expiry

export interface TrustedTimeSyncSnapshot {
  serverTimeMs: number;
  deviceMonotonicMs: number;
  bootId: string;
}

export function evaluateTrustedTime(
  snapshot: TrustedTimeSyncSnapshot | null,
  currentMonotonicMs: number,
  currentBootId: string,
  requiresSyncFlag = false
): { status: TrustedTimeStatus; currentEstimatedServerTimeMs: number | null } {
  if (requiresSyncFlag) {
    return { status: 'REQUIRES_SYNC', currentEstimatedServerTimeMs: null };
  }

  if (!snapshot) {
    return { status: 'REQUIRES_SYNC', currentEstimatedServerTimeMs: null };
  }

  // Check for device reboot or monotonic clock reset
  if (snapshot.bootId !== currentBootId || currentMonotonicMs < snapshot.deviceMonotonicMs) {
    return { status: 'INVALID_AFTER_REBOOT', currentEstimatedServerTimeMs: null };
  }

  const elapsedMs = currentMonotonicMs - snapshot.deviceMonotonicMs;
  if (elapsedMs < 0) {
    return { status: 'INVALID_AFTER_REBOOT', currentEstimatedServerTimeMs: null };
  }

  const currentEstimatedServerTimeMs = snapshot.serverTimeMs + elapsedMs;

  if (elapsedMs >= MAX_OFFLINE_WINDOW_MS) {
    return { status: 'EXPIRED', currentEstimatedServerTimeMs };
  }

  if (MAX_OFFLINE_WINDOW_MS - elapsedMs <= EXPIRING_THRESHOLD_MS) {
    return { status: 'EXPIRING', currentEstimatedServerTimeMs };
  }

  return { status: 'VALID', currentEstimatedServerTimeMs };
}

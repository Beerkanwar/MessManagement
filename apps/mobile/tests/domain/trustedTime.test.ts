// Test Checkpoint: Monotonic time calculation, drift detection, and reboot invalidation
// Domain tests run without any React Native runtime per SDD §6.1, Spike S2, SDD §93
import {
  evaluateTrustedTime,
  TrustedTimeSyncSnapshot,
  MAX_OFFLINE_WINDOW_MS,
  EXPIRING_THRESHOLD_MS,
} from '../../src/domain/time/trustedTime';

describe('Domain: Trusted Time Monotonic Protocol', () => {
  const baseServerTimeMs = 1700000000000;
  const baseMonotonicMs = 50000;
  const bootId = 'boot-uuid-001';

  const snapshot: TrustedTimeSyncSnapshot = {
    serverTimeMs: baseServerTimeMs,
    deviceMonotonicMs: baseMonotonicMs,
    bootId: bootId,
  };

  it('evaluates to VALID when elapsed time is within normal offline window', () => {
    // 2 hours elapsed
    const currentMonotonicMs = baseMonotonicMs + 2 * 60 * 60 * 1000;
    const result = evaluateTrustedTime(snapshot, currentMonotonicMs, bootId);

    expect(result.status).toBe('VALID');
    expect(result.currentEstimatedServerTimeMs).toBe(baseServerTimeMs + 2 * 60 * 60 * 1000);
  });

  it('evaluates to EXPIRING when remaining offline time is under threshold', () => {
    // 71.5 hours elapsed (only 30 min remaining before 72h max)
    const elapsedMs = MAX_OFFLINE_WINDOW_MS - (EXPIRING_THRESHOLD_MS / 2);
    const currentMonotonicMs = baseMonotonicMs + elapsedMs;

    const result = evaluateTrustedTime(snapshot, currentMonotonicMs, bootId);
    expect(result.status).toBe('EXPIRING');
    expect(result.currentEstimatedServerTimeMs).toBe(baseServerTimeMs + elapsedMs);
  });

  it('evaluates to EXPIRED when elapsed monotonic time exceeds 72 hours', () => {
    // 73 hours elapsed
    const elapsedMs = MAX_OFFLINE_WINDOW_MS + (60 * 60 * 1000);
    const currentMonotonicMs = baseMonotonicMs + elapsedMs;

    const result = evaluateTrustedTime(snapshot, currentMonotonicMs, bootId);
    expect(result.status).toBe('EXPIRED');
  });

  it('invalidates immediately after device reboot (bootId changed)', () => {
    const currentMonotonicMs = 10000; // Monotonic reset after reboot
    const newBootId = 'boot-uuid-002'; // New boot session

    const result = evaluateTrustedTime(snapshot, currentMonotonicMs, newBootId);
    expect(result.status).toBe('INVALID_AFTER_REBOOT');
    expect(result.currentEstimatedServerTimeMs).toBeNull();
  });

  it('invalidates when monotonic clock jumps backwards', () => {
    const backwardsMonotonicMs = baseMonotonicMs - 5000; // Clock moved backwards

    const result = evaluateTrustedTime(snapshot, backwardsMonotonicMs, bootId);
    expect(result.status).toBe('INVALID_AFTER_REBOOT');
  });

  it('requires sync when flag is true or snapshot is null', () => {
    const res1 = evaluateTrustedTime(null, baseMonotonicMs, bootId);
    expect(res1.status).toBe('REQUIRES_SYNC');

    const res2 = evaluateTrustedTime(snapshot, baseMonotonicMs + 1000, bootId, true);
    expect(res2.status).toBe('REQUIRES_SYNC');
  });
});

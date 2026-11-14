// Trusted Time State Slice per SDD §126, Build Item 6
import { create } from 'zustand';
import { TrustedTimeStatus } from '../domain/types';
import { evaluateTrustedTime, TrustedTimeSyncSnapshot } from '../domain/time/trustedTime';

export interface TrustedTimeState {
  status: TrustedTimeStatus;
  serverTimeAtSyncMs: number | null;
  monotonicTimeAtSyncMs: number | null;
  bootIdAtSync: string | null;
  estimatedServerTimeMs: number | null;

  setStatus: (status: TrustedTimeStatus) => void;
  recordSyncTime: (serverTimeMs: number, monotonicMs: number, bootId: string) => void;
  evaluate: (currentMonotonicMs: number, currentBootId: string, requiresSync?: boolean) => TrustedTimeStatus;
  reset: () => void;
}

export const useTrustedTimeStore = create<TrustedTimeState>((set, get) => ({
  status: 'REQUIRES_SYNC',
  serverTimeAtSyncMs: null,
  monotonicTimeAtSyncMs: null,
  bootIdAtSync: null,
  estimatedServerTimeMs: null,

  setStatus: (status: TrustedTimeStatus) => set({ status }),

  recordSyncTime: (serverTimeMs: number, monotonicMs: number, bootId: string) => {
    set({
      status: 'VALID',
      serverTimeAtSyncMs: serverTimeMs,
      monotonicTimeAtSyncMs: monotonicMs,
      bootIdAtSync: bootId,
      estimatedServerTimeMs: serverTimeMs,
    });
  },

  evaluate: (currentMonotonicMs: number, currentBootId: string, requiresSync = false) => {
    const state = get();
    let snapshot: TrustedTimeSyncSnapshot | null = null;
    if (state.serverTimeAtSyncMs && state.monotonicTimeAtSyncMs && state.bootIdAtSync) {
      snapshot = {
        serverTimeMs: state.serverTimeAtSyncMs,
        deviceMonotonicMs: state.monotonicTimeAtSyncMs,
        bootId: state.bootIdAtSync,
      };
    }

    const result = evaluateTrustedTime(snapshot, currentMonotonicMs, currentBootId, requiresSync);
    set({
      status: result.status,
      estimatedServerTimeMs: result.currentEstimatedServerTimeMs,
    });
    return result.status;
  },

  reset: () =>
    set({
      status: 'REQUIRES_SYNC',
      serverTimeAtSyncMs: null,
      monotonicTimeAtSyncMs: null,
      bootIdAtSync: null,
      estimatedServerTimeMs: null,
    }),
}));

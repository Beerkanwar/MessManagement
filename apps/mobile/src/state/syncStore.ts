// Sync State Slice per SDD §126, Build Item 6
import { create } from 'zustand';
import { SyncStatus } from '../domain/types';

export interface SyncState {
  status: SyncStatus;
  pendingUploadCount: number;
  lastSyncAt: string | null;
  errorMessage: string | null;

  setStatus: (status: SyncStatus, errorMessage?: string | null) => void;
  setPendingUploadCount: (count: number) => void;
  setLastSyncAt: (timestamp: string) => void;
  reset: () => void;
}

export const useSyncStore = create<SyncState>((set) => ({
  status: 'IDLE',
  pendingUploadCount: 0,
  lastSyncAt: null,
  errorMessage: null,

  setStatus: (status: SyncStatus, errorMessage: string | null = null) =>
    set({ status, errorMessage }),
  setPendingUploadCount: (pendingUploadCount: number) => set({ pendingUploadCount }),
  setLastSyncAt: (lastSyncAt: string) => set({ lastSyncAt }),
  reset: () =>
    set({
      status: 'IDLE',
      pendingUploadCount: 0,
      lastSyncAt: null,
      errorMessage: null,
    }),
}));

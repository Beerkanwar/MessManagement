// Connectivity State Slice per SDD §94, SDD §126 (A hint only, never a global gate)
import { create } from 'zustand';

export interface ConnectivityState {
  isOnline: boolean;
  connectionType: string | null;
  lastCheckedAt: string;
  setConnectivity: (isOnline: boolean, connectionType?: string | null) => void;
}

export const useConnectivityStore = create<ConnectivityState>((set) => ({
  isOnline: true,
  connectionType: null,
  lastCheckedAt: new Date().toISOString(),

  setConnectivity: (isOnline: boolean, connectionType: string | null = null) =>
    set({
      isOnline,
      connectionType,
      lastCheckedAt: new Date().toISOString(),
    }),
}));

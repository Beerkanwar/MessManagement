// Manager Authorization State Slice per SDD §126, Build Item 6
import { create } from 'zustand';
import { ManagerAuthorizationStatus } from '../domain/types';

export interface AuthorizationState {
  status: ManagerAuthorizationStatus;
  validUntil: string | null;
  graceUntil: string | null;
  offlineWindowHours: number;

  setStatus: (status: ManagerAuthorizationStatus) => void;
  setAuthorizationWindow: (validUntil: string, graceUntil: string, hours: number) => void;
  reset: () => void;
}

export const useAuthorizationStore = create<AuthorizationState>((set) => ({
  status: 'ACTIVE',
  validUntil: null,
  graceUntil: null,
  offlineWindowHours: 72,

  setStatus: (status: ManagerAuthorizationStatus) => set({ status }),
  setAuthorizationWindow: (validUntil: string, graceUntil: string, hours: number) =>
    set({ validUntil, graceUntil, offlineWindowHours: hours }),
  reset: () =>
    set({
      status: 'ACTIVE',
      validUntil: null,
      graceUntil: null,
      offlineWindowHours: 72,
    }),
}));

// Meal Session State Slice per SDD §126, Build Item 6
import { create } from 'zustand';
import { MealType } from '../domain/types';

export interface MealSessionState {
  isSessionActive: boolean;
  mealType: MealType | null;
  mealDate: string | null;
  sessionStartTime: string | null;
  scannedCount: number;

  startSession: (mealType: MealType, mealDate: string) => void;
  endSession: () => void;
  incrementScannedCount: () => void;
  reset: () => void;
}

export const useMealSessionStore = create<MealSessionState>((set) => ({
  isSessionActive: false,
  mealType: null,
  mealDate: null,
  sessionStartTime: null,
  scannedCount: 0,

  startSession: (mealType: MealType, mealDate: string) =>
    set({
      isSessionActive: true,
      mealType,
      mealDate,
      sessionStartTime: new Date().toISOString(),
      scannedCount: 0,
    }),

  endSession: () =>
    set({
      isSessionActive: false,
      mealType: null,
      mealDate: null,
      sessionStartTime: null,
      scannedCount: 0,
    }),

  incrementScannedCount: () =>
    set((state) => ({ scannedCount: state.scannedCount + 1 })),

  reset: () =>
    set({
      isSessionActive: false,
      mealType: null,
      mealDate: null,
      sessionStartTime: null,
      scannedCount: 0,
    }),
}));

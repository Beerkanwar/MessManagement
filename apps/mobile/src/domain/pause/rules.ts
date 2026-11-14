// Domain Pause Rules - Pure TypeScript (Zero React Native imports) per SDD §6.1, Phase 9
import { MealType } from '../types';

export const QUALIFYING_MEALS: readonly MealType[] = ['BREAKFAST', 'LUNCH', 'DINNER'] as const;

export function isQualifyingMeal(meal: MealType): boolean {
  return meal === 'BREAKFAST' || meal === 'LUNCH' || meal === 'DINNER';
}

/**
 * Calculates remaining qualifying slots between current meal slot and target meal slot.
 * Minimum notice required for pause creation is 3 qualifying slots.
 */
export function meetsPauseNoticeRequirement(qualifyingSlotsRemaining: number): boolean {
  return qualifyingSlotsRemaining >= 3;
}

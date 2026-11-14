// Domain Types - Pure TypeScript (Zero React Native imports) per SDD §6.1

export type UserRole = 'STUDENT' | 'MESS_MANAGER' | 'HOSTEL_CLERK' | 'SUPER_ADMIN';

export interface User {
  id: number;
  email: string;
  full_name: string;
  phone_number?: string;
}

export interface AssignmentSummary {
  hostel_id?: number;
  hostel_name?: string;
  mess_id?: number;
  mess_name?: string;
  roll_number?: string;
  room_number?: string;
  staff_id?: string;
}

export interface DeviceSummary {
  device_id: string;
  device_name?: string;
  platform: string;
  last_seen_at?: string;
}

export type VersionPolicyStatus = 'SUPPORTED' | 'DEPRECATED' | 'BLOCKED';

export interface VersionPolicy {
  status: VersionPolicyStatus;
  force_update_message?: string;
}

export class AppError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details?: Record<string, any>;

  constructor(
    message: string,
    code = 'UNKNOWN_ERROR',
    status = 500,
    details?: Record<string, any>
  ) {
    super(message);
    this.name = 'AppError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

// State Slice Enums per SDD §126
export type AuthStatus = 'SIGNED_OUT' | 'RESTORING' | 'SIGNED_IN';

export type ManagerAuthorizationStatus =
  | 'ACTIVE'
  | 'OFFLINE_NORMAL'
  | 'OFFLINE_GRACE'
  | 'SYNC_REQUIRED'
  | 'REVOKE_PENDING_SYNC'
  | 'REVOKED';

export type SyncStatus =
  | 'IDLE'
  | 'CHECKING'
  | 'UPLOADING'
  | 'DOWNLOADING'
  | 'SUCCESS'
  | 'RETRYING'
  | 'CONFLICT'
  | 'BLOCKED';

export type TrustedTimeStatus =
  | 'VALID'
  | 'EXPIRING'
  | 'EXPIRED'
  | 'REQUIRES_SYNC'
  | 'INVALID_AFTER_REBOOT';

export type MealType = 'BREAKFAST' | 'LUNCH' | 'SNACKS' | 'DINNER';

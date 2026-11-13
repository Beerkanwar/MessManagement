/**
 * API Type Definitions [SPEC SDD §11, §64, §88].
 */

export type UserRole = 'SUPER_ADMIN' | 'HOSTEL_CLERK' | 'MESS_MANAGER' | 'STUDENT';

export interface UserSummary {
  user_id: string | number;
  email: string;
  full_name: string;
}

export interface UserAssignmentSummary {
  hostel_id?: number;
  hostel_name?: string;
  mess_id?: number;
  mess_name?: string;
  assignment_id?: number;
  status?: string;
}

export interface DeviceSummary {
  device_registration_id?: number;
  device_id: string;
  platform: string;
  session_status: string;
  last_active_at?: string;
}

export interface AuthTokens {
  access: string;
  refresh?: string;
  expires_in: number;
}

export interface LoginResponse {
  user: UserSummary;
  role: UserRole;
  assignment?: UserAssignmentSummary;
  device?: DeviceSummary;
  tokens: AuthTokens;
}

export interface UserProfileResponse {
  user: UserSummary;
  role: UserRole;
  assignment?: UserAssignmentSummary;
  device?: DeviceSummary;
}

export interface ApiErrorEnvelope {
  error: {
    code: string;
    message: string;
    trace_id?: string;
    details?: Record<string, string[] | string>;
  };
}

export interface ClerkDashboardStats {
  pendingVerifications: number;
  menuStatusThisMonth: 'DRAFT' | 'PUBLISHED' | 'MISSING';
  menuStatusNextMonth: 'DRAFT' | 'PUBLISHED' | 'MISSING';
  recentFeedbackAverage: number;
  billsReadyCount: number;
}

export interface SuperAdminDashboardStats {
  studentsAwaitingVerification: number;
  billingPeriodStatus: 'OPEN' | 'BILL_GENERATED' | 'REVIEWED' | 'LOCKED';
  openSyncConflicts: number;
  oldestSyncDeviceHours: number;
  unresolvedImportErrors: number;
}


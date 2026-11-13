/**
 * Normalized Application Error and Error Catalog [SPEC SDD §88, §89, ImplementationGuide Phase 15].
 */

export interface FieldErrors {
  [fieldName: string]: string[] | string;
}

export class AppError extends Error {
  readonly code: string;
  readonly traceId?: string;
  readonly status: number;
  readonly fieldErrors?: FieldErrors;

  constructor(params: {
    code: string;
    message: string;
    status: number;
    traceId?: string;
    fieldErrors?: FieldErrors;
  }) {
    super(params.message);
    this.name = 'AppError';
    this.code = params.code;
    this.status = params.status;
    this.traceId = params.traceId;
    this.fieldErrors = params.fieldErrors;
  }
}

/**
 * Friendly user messages catalog for known API error codes [REC].
 */
export const ERROR_MESSAGES: Record<string, string> = {
  UNAUTHENTICATED: 'Your session has expired. Please sign in again.',
  TOKEN_EXPIRED: 'Your session has expired. Please sign in again.',
  INVALID_TOKEN: 'Session verification failed. Please sign in again.',
  PERMISSION_DENIED: 'You do not have permission to perform this action.',
  FORBIDDEN: 'Access denied.',
  WRONG_CLIENT: 'Students and Mess Managers must sign in using the mobile app.',
  DEVICE_REVOKED: 'You signed in on another device. Please sign in again.',
  DEVICE_REPLACED: 'You signed in on another device. Please sign in again.',
  VERSION_CONFLICT: 'This record was changed by someone else. Please reload and try again.',
  CONFLICT: 'This action conflicts with the current record state.',
  NOT_FOUND: 'The requested resource was not found.',
  RATE_LIMIT_EXCEEDED: 'Too many requests. Please wait a moment and try again.',
  VALIDATION_ERROR: 'Please check the highlighted fields and correct any errors.',
  INTERNAL_SERVER_ERROR: 'A server error occurred. Please try again or contact support.',
  NETWORK_ERROR: 'Network error. Please check your internet connection.',
};

export function getErrorMessage(code: string, fallbackMessage?: string): string {
  if (ERROR_MESSAGES[code]) {
    return ERROR_MESSAGES[code];
  }
  return fallbackMessage || 'An unexpected error occurred. Please try again.';
}


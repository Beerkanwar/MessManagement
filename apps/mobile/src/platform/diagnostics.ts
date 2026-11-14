// Diagnostics Ring Buffer with Strict Redaction per SDD §7, ImplementationGuide Build 9

export type LogLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR';

export interface LogEntry {
  id: number;
  timestamp: string;
  level: LogLevel;
  tag: string;
  message: string;
  data?: any;
}

const MAX_ENTRIES = 100;
const SENSITIVE_KEY_PATTERN = /(password|passwd|secret|token|access_token|refresh_token|authorization|cookie|otp|code|qr_payload|raw_qr|hmac|seed|private_key)/i;
const JWT_PATTERN = /eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+/g;
const BEARER_PATTERN = /Bearer\s+[a-zA-Z0-9_.-]+/gi;
const QR_PIPE_PATTERN = /([A-Za-z0-9_-]+)\|(\d{6})/g;

export function redactString(str: string): string {
  if (!str) return str;
  return str
    .replace(BEARER_PATTERN, 'Bearer [REDACTED]')
    .replace(JWT_PATTERN, '[REDACTED_TOKEN]')
    .replace(QR_PIPE_PATTERN, '$1|[REDACTED_CODE]');
}

export function redactValue(val: any, parentKey?: string): any {
  if (val === null || val === undefined) {
    return val;
  }

  if (parentKey && SENSITIVE_KEY_PATTERN.test(parentKey)) {
    return '[REDACTED]';
  }

  if (typeof val === 'string') {
    return redactString(val);
  }

  if (typeof val === 'number' || typeof val === 'boolean') {
    return val;
  }

  if (Array.isArray(val)) {
    return val.map((item) => redactValue(item, parentKey));
  }

  if (typeof val === 'object') {
    if (val instanceof Error) {
      return {
        name: val.name,
        message: redactString(val.message),
        stack: val.stack ? redactString(val.stack) : undefined,
      };
    }
    const cleanObj: Record<string, any> = {};
    for (const [k, v] of Object.entries(val)) {
      if (SENSITIVE_KEY_PATTERN.test(k)) {
        cleanObj[k] = '[REDACTED]';
      } else {
        cleanObj[k] = redactValue(v, k);
      }
    }
    return cleanObj;
  }

  return val;
}

class DiagnosticsLogger {
  private entries: LogEntry[] = [];
  private nextId = 1;

  public log(level: LogLevel, tag: string, message: string, data?: any): void {
    const entry: LogEntry = {
      id: this.nextId++,
      timestamp: new Date().toISOString(),
      level,
      tag: redactString(tag),
      message: redactString(message),
      data: data !== undefined ? redactValue(data) : undefined,
    };

    this.entries.push(entry);
    if (this.entries.length > MAX_ENTRIES) {
      this.entries.shift();
    }
  }

  public debug(tag: string, message: string, data?: any): void {
    this.log('DEBUG', tag, message, data);
  }

  public info(tag: string, message: string, data?: any): void {
    this.log('INFO', tag, message, data);
  }

  public warn(tag: string, message: string, data?: any): void {
    this.log('WARN', tag, message, data);
  }

  public error(tag: string, message: string, data?: any): void {
    this.log('ERROR', tag, message, data);
  }

  public getEntries(): readonly LogEntry[] {
    return [...this.entries];
  }

  public clear(): void {
    this.entries = [];
  }

  public exportAsString(): string {
    return this.entries
      .map((e) => `[${e.timestamp}] [${e.level}] [${e.tag}] ${e.message}${e.data ? ` | ${JSON.stringify(e.data)}` : ''}`)
      .join('\n');
  }
}

export const logger = new DiagnosticsLogger();

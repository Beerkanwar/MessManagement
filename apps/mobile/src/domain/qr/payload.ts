// Domain QR Payload - Pure TypeScript (Zero React Native imports) per SDD §6.1, SDD §19-21
import { hmac } from '@noble/hashes/hmac';
import { sha256 } from '@noble/hashes/sha256';

export interface ParsedQrPayload {
  rollNumber: string;
  code: string;
}

export function parsePayload(payload: string): ParsedQrPayload {
  if (typeof payload !== 'string') {
    throw new Error('QR payload must be a string');
  }

  const parts = payload.split('|');
  if (parts.length !== 2) {
    throw new Error('Invalid QR payload format: must contain exactly one pipe delimiter');
  }

  const rollNumber = parts[0].trim();
  const code = parts[1].trim();

  if (!rollNumber) {
    throw new Error('Roll number cannot be empty in QR payload');
  }

  if (!/^\d{6}$/.test(code)) {
    throw new Error('QR code component must be exactly 6 numeric digits');
  }

  return { rollNumber, code };
}

export function formatPayload(rollNumber: string, code: string): string {
  const cleanRoll = rollNumber.trim();
  const cleanCode = code.trim();
  if (!cleanRoll) throw new Error('Roll number cannot be empty');
  if (!/^\d{6}$/.test(cleanCode)) throw new Error('QR code must be 6 numeric digits');
  return `${cleanRoll}|${cleanCode}`;
}

export function isValidPayloadFormat(payload: string): boolean {
  try {
    parsePayload(payload);
    return true;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// TOTP QR Protocol Functions [SPEC SDD §19-21, SRS §9]
// ---------------------------------------------------------------------------

export function computeCounter(unixSeconds: number, step = 30): bigint {
  if (step <= 0) {
    throw new Error('Time step must be positive');
  }
  return BigInt(Math.floor(unixSeconds / step));
}

export function counterToBytes(counter: bigint): Uint8Array {
  if (counter < 0n) {
    throw new Error('Counter cannot be negative');
  }
  const buffer = new ArrayBuffer(8);
  const view = new DataView(buffer);
  view.setBigUint64(0, counter, false); // false = big-endian
  return new Uint8Array(buffer);
}

export function computeCode(secretBytes: Uint8Array, counter: bigint): string {
  const counterBytes = counterToBytes(counter);
  const mac = hmac(sha256, secretBytes, counterBytes);

  // Dynamic truncation per SPEC SDD §20.3
  const offset = mac[mac.length - 1] & 0x0f;
  const view = new DataView(mac.buffer, mac.byteOffset, mac.byteLength);
  const rawInt = view.getUint32(offset, false); // big-endian
  const truncated = rawInt & 0x7fffffff;
  const codeInt = truncated % 1_000_000;

  return codeInt.toString().padStart(6, '0');
}

export function computeCodeForTime(
  secretBytes: Uint8Array,
  unixSeconds: number,
  step = 30
): string {
  const counter = computeCounter(unixSeconds, step);
  return computeCode(secretBytes, counter);
}

export function generatePayload(
  rollNumber: string,
  secretBytes: Uint8Array,
  unixSeconds: number,
  step = 30
): string {
  const code = computeCodeForTime(secretBytes, unixSeconds, step);
  return formatPayload(rollNumber, code);
}

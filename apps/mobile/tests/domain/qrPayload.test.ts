// Test Checkpoint: QR Payload parsing, formatting, and cryptographic TOTP protocol
// Domain tests run without any React Native runtime per SDD §6.1, Spike S3, SDD §19-21
import {
  parsePayload,
  formatPayload,
  isValidPayloadFormat,
  computeCounter,
  computeCode,
  computeCodeForTime,
  generatePayload,
} from '../../src/domain/qr/payload';

function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hex.substring(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}

describe('Domain: QR Payload Parsing and Formatting', () => {
  it('parses valid payload ROLL|CODE', () => {
    const parsed = parsePayload('21BCE1001|123456');
    expect(parsed.rollNumber).toBe('21BCE1001');
    expect(parsed.code).toBe('123456');
    expect(isValidPayloadFormat('21BCE1001|123456')).toBe(true);
  });

  it('rejects malformed payloads', () => {
    expect(() => parsePayload('21BCE1001')).toThrow('must contain exactly one pipe delimiter');
    expect(() => parsePayload('21BCE1001|12345|EXTRA')).toThrow('must contain exactly one pipe delimiter');
    expect(() => parsePayload('|123456')).toThrow('Roll number cannot be empty');
    expect(() => parsePayload('21BCE1001|12345')).toThrow('must be exactly 6 numeric digits');
    expect(() => parsePayload('21BCE1001|abcdef')).toThrow('must be exactly 6 numeric digits');
  });

  it('formats roll number and code into valid canonical payload', () => {
    const formatted = formatPayload('21BCE1001', '654321');
    expect(formatted).toBe('21BCE1001|654321');
    expect(isValidPayloadFormat(formatted)).toBe(true);
  });
});

describe('Domain: Cryptographic TOTP vectors from docs/test-vectors/qr-v1.json', () => {
  const secretHex = '544553545f53545544454e545f5345435245545f4b45595f3332425954455321';
  const secretBytes = hexToBytes(secretHex);

  it('computes counter accurately', () => {
    expect(computeCounter(0, 30)).toBe(0n);
    expect(computeCounter(29, 30)).toBe(0n);
    expect(computeCounter(30, 30)).toBe(1n);
    expect(computeCounter(59, 30)).toBe(1n);
    expect(computeCounter(60, 30)).toBe(2n);
  });

  it('matches awkward case 1: unix_time 0 -> code 753579', () => {
    const code = computeCodeForTime(secretBytes, 0, 30);
    expect(code).toBe('753579');
  });

  it('matches awkward case 2: unix_time 29 -> code 753579', () => {
    const code = computeCodeForTime(secretBytes, 29, 30);
    expect(code).toBe('753579');
  });

  it('matches awkward case 3: unix_time 30 -> code 681874', () => {
    const code = computeCodeForTime(secretBytes, 30, 30);
    expect(code).toBe('681874');
  });

  it('generates full payload ROLL|CODE correctly', () => {
    const payload = generatePayload('23103030', secretBytes, 0, 30);
    expect(payload).toBe('23103030|753579');
    expect(isValidPayloadFormat(payload)).toBe(true);
  });
});

// Test Checkpoint: Diagnostics ring-buffer and strict redaction
// "Search of the log buffer and Diagnostics output for tokens, passwords and secrets finds nothing."
import { logger } from '../../src/platform/diagnostics';

describe('Platform: Diagnostics Ring-Buffer and Redaction', () => {
  beforeEach(() => {
    logger.clear();
  });

  it('enforces maximum 100 entries in the ring buffer', () => {
    for (let i = 0; i < 120; i++) {
      logger.info('TestTag', `Message ${i}`);
    }

    const entries = logger.getEntries();
    expect(entries.length).toBe(100);
    expect(entries[0].message).toBe('Message 20');
    expect(entries[99].message).toBe('Message 119');
  });

  it('strictly redacts sensitive keys and values in log data and messages', () => {
    // Attempt logging passwords, tokens, secrets, OTPs, QR payloads
    logger.info('Auth', 'User logged in with credentials', {
      username: 'student@mess.edu',
      password: 'SuperSecretPassword123!',
      access_token: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjoxfQ.signature123',
      refresh_token: 'secret_opaque_refresh_token_9999',
      otp: '654321',
      qr_payload: '21BCE1001|753579',
      secret: 'hex_secret_student_key_32bytes',
    });

    logger.warn('Auth', 'Failed bearer token: Bearer eyJabc123.def456.ghi789 and raw QR: 21BCE1001|123456');

    const rawExport = logger.exportAsString();
    const entries = logger.getEntries();

    // Verify nothing sensitive exists in exported string or entries
    expect(rawExport).not.toContain('SuperSecretPassword123!');
    expect(rawExport).not.toContain('secret_opaque_refresh_token_9999');
    expect(rawExport).not.toContain('hex_secret_student_key_32bytes');
    expect(rawExport).not.toContain('21BCE1001|753579');
    expect(rawExport).not.toContain('21BCE1001|123456');
    expect(rawExport).not.toContain('eyJabc123.def456.ghi789');

    // Confirm redaction placeholders are used
    expect(rawExport).toContain('[REDACTED]');
    expect(rawExport).toContain('[REDACTED_CODE]');

    const data = entries[0].data;
    expect(data.password).toBe('[REDACTED]');
    expect(data.access_token).toBe('[REDACTED]');
    expect(data.refresh_token).toBe('[REDACTED]');
    expect(data.otp).toBe('[REDACTED]');
    expect(data.qr_payload).toBe('[REDACTED]');
    expect(data.secret).toBe('[REDACTED]');
  });
});

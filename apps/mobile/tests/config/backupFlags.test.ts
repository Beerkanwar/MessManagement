// Test Checkpoint 7: Backup exclusion flags & permissions verified in app.config.ts
import appConfigFactory from '../../app.config';

describe('Project Configuration & Backup Flags (Build Item 1 & 2)', () => {
  const config = appConfigFactory({} as any);

  it('verifies Android allowBackup is disabled and data extraction rules exclude backups', () => {
    expect(config.android?.allowBackup).toBe(false);
    expect(config.android?.dataExtractionRules).toEqual({
      cloudBackup: false,
      deviceToDeviceTransfer: false,
    });
  });

  it('verifies camera is the ONLY requested Android permission (no location, contacts, storage)', () => {
    expect(config.android?.permissions).toEqual(['android.permission.CAMERA']);
    expect(config.android?.permissions).not.toContain('android.permission.ACCESS_FINE_LOCATION');
    expect(config.android?.permissions).not.toContain('android.permission.READ_CONTACTS');
    expect(config.android?.permissions).not.toContain('android.permission.READ_EXTERNAL_STORAGE');
  });

  it('verifies portrait lock and application identifiers', () => {
    expect(config.orientation).toBe('portrait');
    expect(config.android?.package).toBe('com.mess.mobile');
    expect(config.ios?.bundleIdentifier).toBe('com.mess.mobile');
    expect(config.scheme).toBe('messapp');
  });

  it('verifies build-time API base URL configuration in extra', () => {
    expect(config.extra?.apiUrl).toBeDefined();
    expect(typeof config.extra?.apiUrl).toBe('string');
  });
});

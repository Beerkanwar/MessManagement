/**
 * Persistent device identity management for Web client [SPEC SDD §11, DEC-10].
 * Generates and stores a unique UUIDv4 in localStorage, platform WEB.
 */

const STORAGE_KEY = 'mess_web_device_id';

function generateUUID(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export function getDeviceId(): string {
  try {
    let id = localStorage.getItem(STORAGE_KEY);
    if (!id) {
      id = generateUUID();
      localStorage.setItem(STORAGE_KEY, id);
    }
    return id;
  } catch {
    return 'fallback-web-device-' + Date.now();
  }
}

export interface DeviceInfo {
  device_id: string;
  platform: 'WEB';
  app_version: string;
  device_name: string;
}

export function getDeviceInfo(appVersion = '1.0.0'): DeviceInfo {
  return {
    device_id: getDeviceId(),
    platform: 'WEB',
    app_version: appVersion,
    device_name: `Web Client (${navigator.userAgent.slice(0, 40)})`,
  };
}


// Device Platform Adapter per SDD §7, Build 9
import { Platform } from 'react-native';
import * as Device from 'expo-device';
import * as Application from 'expo-application';
import * as Crypto from 'expo-crypto';
import { ISecureStorage } from '../data/storage/secureStorage';

export interface DeviceInfo {
  deviceId: string;
  deviceName: string;
  platform: 'ANDROID' | 'IOS';
  appVersion: string;
  isRootedOrJailbroken: boolean;
}

const DEVICE_ID_KEY = 'mess_device_unique_id';

export async function getOrCreateDeviceIdAsync(storage: ISecureStorage): Promise<string> {
  const existing = await storage.getItemAsync(DEVICE_ID_KEY);
  if (existing) {
    return existing;
  }
  const newId = Crypto.randomUUID ? Crypto.randomUUID() : `dev-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
  await storage.setItemAsync(DEVICE_ID_KEY, newId);
  return newId;
}

export function getPlatform(): 'ANDROID' | 'IOS' {
  return Platform.OS === 'ios' ? 'IOS' : 'ANDROID';
}

export function getAppVersion(): string {
  return Application.nativeApplicationVersion || '1.0.0';
}

export function getDeviceName(): string {
  return Device.modelName || (Platform.OS === 'ios' ? 'iPhone' : 'Android Device');
}

export async function checkRootOrJailbreakAsync(): Promise<boolean> {
  try {
    if (Device.isRootedExperimentalAsync) {
      return await Device.isRootedExperimentalAsync();
    }
  } catch {
    // Best-effort check; fallback to false
  }
  return false;
}

export async function getDeviceInfoAsync(storage: ISecureStorage): Promise<DeviceInfo> {
  const deviceId = await getOrCreateDeviceIdAsync(storage);
  const isRootedOrJailbroken = await checkRootOrJailbreakAsync();
  return {
    deviceId,
    deviceName: getDeviceName(),
    platform: getPlatform(),
    appVersion: getAppVersion(),
    isRootedOrJailbroken,
  };
}

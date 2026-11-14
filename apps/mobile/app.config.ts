import { ExpoConfig, ConfigContext } from 'expo/config';

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: 'Hostel Mess Management',
  slug: 'mess-mobile',
  version: '1.0.0',
  orientation: 'portrait',
  scheme: 'messapp',
  userInterfaceStyle: 'light',
  ios: {
    supportsTablet: false,
    bundleIdentifier: 'com.mess.mobile',
    infoPlist: {
      NSCameraUsageDescription: 'Camera access is required for Mess Managers to scan student meal QR codes.',
      UIRequiresFullScreen: true,
    },
  },
  android: {
    package: 'com.mess.mobile',
    permissions: [
      'android.permission.CAMERA',
    ],
    allowBackup: false,
    dataExtractionRules: {
      cloudBackup: false,
      deviceToDeviceTransfer: false,
    },
  },
  plugins: [
    [
      'expo-camera',
      {
        cameraPermission: 'Camera access is required for Mess Managers to scan student meal QR codes.',
      },
    ],
    'expo-secure-store',
    'expo-screen-capture',
  ],
  extra: {
    apiUrl: process.env.EXPO_PUBLIC_API_URL || 'http://10.0.2.2:8000/api/v1',
    eas: {
      projectId: 'mess-mobile-foundation',
    },
  },
});

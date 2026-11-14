# Mobile Development Workflow & Dev Client Guide

This document describes how to configure, build, install, and run the **Hostel Mess Management** mobile application (`apps/mobile`) using Expo SDK 51 and EAS Build per **SPEC SDD §7, SDD §144**, and **ImplementationGuide Phase 18**.

---

## 1. Architecture & Native Code Prerequisites

The mobile application utilizes native code modules:
- `op-sqlite` with SQLCipher (native cryptographic C++ SQLite runtime for offline database storage and scanning)
- `expo-camera` (hardware camera access for meal QR scanning)
- `expo-secure-store` (`kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly` keychain & Keystore isolation)
- `expo-screen-capture` (hardware screenshot protection for dynamic QR codes)

> [!IMPORTANT]
> Because `op-sqlite` and custom native adapters require compiled native binaries, **Expo Go cannot run this application**. You must use a **development build** (`expo-dev-client`) created via EAS Build or local prebuild.

---

## 2. Building the Development Client

Project configuration is managed through `apps/mobile/app.config.ts` and `apps/mobile/eas.json`.

### A. Android Development Client (APK)

#### Option 1: EAS Cloud Build (Recommended)
1. Log in to your Expo account:
   ```bash
   eas login
   ```
2. Run EAS build with the `development` profile:
   ```bash
   cd apps/mobile
   eas build --profile development --platform android
   ```
3. EAS will produce an installable standalone `.apk`.
4. Install on physical devices or emulator:
   ```bash
   adb install path/to/mess-mobile-development.apk
   ```

#### Option 2: Local Native Build
Ensure Android Studio, Android SDK 34, and an emulator or USB-debugging device are available:
```bash
cd apps/mobile
npx expo run:android
```

---

### B. iOS Development Client

#### Requirements
1. An Apple Developer account (Individual or Organization).
2. Physical test devices registered on your Apple Developer portal.

#### Steps
1. Register physical test devices with EAS:
   ```bash
   eas device:create
   ```
2. Build the development client using ad-hoc provisioning:
   ```bash
   cd apps/mobile
   eas build --profile development --platform ios
   ```
3. For iOS Simulators:
   ```bash
   eas build --profile development --platform ios --simulator
   # Or locally:
   npx expo run:ios
   ```

---

## 3. Connecting to the Local Backend API

Development builds allow cleartext HTTP traffic to local network IP addresses.

### 1. Identify Your Development Server IP
On Windows, check your Wi-Fi or LAN IPv4 address:
```powershell
ipconfig
# Note your IPv4 Address, e.g., 192.168.1.45
```

### 2. Configure Backend Django Server
Ensure Django backend accepts connections from your local subnet in `.env`:
```env
ALLOWED_HOSTS=localhost,127.0.0.1,10.0.2.2,192.168.1.*
```
Run Django server listening on all network interfaces:
```bash
python manage.py runserver 0.0.0.0:8000
```

### 3. Point the Mobile App to Local API
You can pass the API URL via `EXPO_PUBLIC_API_URL` or edit `apps/mobile/eas.json`:
- **Android Emulator**: `http://10.0.2.2:8000/api/v1`
- **Physical Device**: `http://192.168.1.45:8000/api/v1`
- **iOS Simulator**: `http://localhost:8000/api/v1`

Start the Expo bundler:
```bash
cd apps/mobile
npx expo start --dev-client
```
Scan the QR code in the terminal or dev menu to load JavaScript bundles into the installed dev client.

---

## 4. Device Management and Session Resetting

### Single Active Device Enforcement (SDD §11)
- Active mobile sessions are limited to **one device at a time**.
- Signing in on Phone B automatically marks Phone A's device registration as `REPLACED` (revocation reason `NEW_DEVICE_LOGIN`) on the backend.
- Phone A detects the replacement upon next token refresh and immediately routes to `DeviceReplacedScreen` ("Signed in on another phone").

### Resetting Device Session
To test clean sign-in states or reset credentials:
1. **In-App Sign Out**: Tap "Sign Out" from Student or Manager Hub. This calls `/auth/logout`, purges the secure refresh token, and resets state.
2. **Clear Application Storage**:
   - **Android**: Long-press app icon $\to$ App Info $\to$ Storage & cache $\to$ "Clear storage".
   - **iOS**: Delete and reinstall the development build, or trigger Diagnostics "Clear Logs".
3. **Admin Device Revocation**:
   Admins can revoke a compromised or lost device via:
   `POST /api/v1/admin/devices/<device_id>/revoke`

---

## 5. Automated Tests and Quality Gates

Run the automated mobile test suite:
```bash
cd apps/mobile
npm test
```

Run TypeScript strict type checking:
```bash
cd apps/mobile
npx tsc --noEmit
```

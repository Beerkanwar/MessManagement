# Mobile Application (@mess/mobile)

Cross-platform React Native client built with **Expo SDK 51**, TypeScript, React Navigation Native Stack, and Zustand for the **Hostel Mess Management System**.

A single unified binary serves both **Student** and **Mess Manager** roles per **SPEC SDD §144**, dynamically routed based on server authentication.

---

## Architecture Layout (SDD §7)

```
apps/mobile/
├── App.tsx                     # Main application entry point (Providers, StatusBar, RootNavigator)
├── app.config.ts               # Expo configuration (bundle ID, backup exclusion, permissions)
├── eas.json                    # EAS build profiles (development, staging, production)
├── src/
│   ├── components/             # Reusable UI component library (Phase 14 design system)
│   ├── design/                 # Design tokens (colors, spacing, radius, typography)
│   ├── domain/                 # Pure TypeScript domain models (ZERO React Native imports, runs in Node)
│   │   ├── auth/               # Role scoping (roles.ts) and Version Policy DEC-18 (versionPolicy.ts)
│   │   ├── pause/              # Advance meal pause notice rules (rules.ts)
│   │   ├── qr/                 # TOTP QR payload HMAC-SHA256 calculations (payload.ts)
│   │   ├── time/               # Monotonic trusted time drift & reboot invalidation (trustedTime.ts)
│   │   └── types.ts            # Domain entity interfaces and normalized AppError
│   ├── data/                   # Data layer
│   │   ├── api/                # API client with in-memory tokens, concurrent 401 mutex, headers
│   │   ├── db/                 # SQLite / SQLCipher database abstraction interfaces
│   │   └── storage/            # Secure storage interfaces (expo-secure-store + InMemory mock)
│   ├── platform/               # Hardware and OS platform adapters
│   │   ├── diagnostics.ts      # Redacted 100-event ring buffer logger (no passwords, tokens, QR)
│   │   ├── device.ts           # Device UUID, model, platform, and root/jailbreak detection
│   │   ├── network.ts          # NetInfo connectivity listener
│   │   ├── screenCapture.ts    # Screenshot prevention adapter for dynamic QR codes
│   │   └── time.ts             # Monotonic clock and boot ID provider
│   ├── state/                  # Typed Zustand state slices (SDD §126)
│   │   ├── authStore.ts        # SIGNED_OUT, RESTORING, SIGNED_IN
│   │   ├── connectivityStore.ts# Online/offline hint
│   │   ├── authorizationStore.ts# Manager offline auth lifecycle
│   │   ├── syncStore.ts        # Sync status and pending upload counters
│   │   ├── trustedTimeStore.ts # Monotonic time status (VALID, EXPIRING, EXPIRED, etc.)
│   │   └── mealSessionStore.ts # Active manager scanning session
│   ├── features/               # Screen features
│   │   ├── auth/               # SignIn, ForgotPassword (3-step), ChangePassword, DeviceReplaced, UpdateRequired, WebRole
│   │   ├── student/            # StudentHomeScreen (7 destinations per App Flow §3)
│   │   ├── manager/            # ManagerHomeScreen (6 destinations per App Flow §4)
│   │   ├── diagnostics/        # DiagnosticsScreen (redacted log viewer, dump exporter)
│   │   └── common/             # DeprecatedVersionBanner (DEC-18)
│   └── navigation/             # Navigation stacks (RootNavigator, AuthStack, StudentStack, ManagerStack)
└── tests/                      # Jest unit test suite (37 tests across domain, state, data, and platform)
```

---

## Development Scripts

From `apps/mobile`:

```bash
# Run unit test suite
npm test

# Run TypeScript type check
npx tsc --noEmit

# Start Expo development server (requires development build)
npm start

# Build or run development client locally
npx expo run:android
npx expo run:ios
```

Detailed developer workflow and installation instructions are available in [docs/mobile/dev_workflow.md](../../docs/mobile/dev_workflow.md).

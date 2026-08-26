# react-native-expo-setup

**Issue:** Bootstrapping a React Native project with Expo and configuring it for production
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Starting a new React Native project requires choosing between bare React Native and Expo. Expo simplifies tooling but has trade-offs around native module access and build times.

## Pattern / Solution
```bash
# Create with Expo (recommended starting point)
npx create-expo-app@latest MyApp --template blank-typescript

# Or with router already wired
npx create-expo-app@latest MyApp --template tabs

# Run on device
npx expo start --tunnel   # works behind NAT
npx expo run:ios          # ejects to native build
npx expo run:android
```

`app.json` / `app.config.ts` key fields:
```json
{
  "expo": {
    "name": "MyApp",
    "slug": "my-app",
    "version": "1.0.0",
    "runtimeVersion": { "policy": "appVersion" },
    "ios": { "bundleIdentifier": "com.example.myapp", "supportsTablet": true },
    "android": { "package": "com.example.myapp", "adaptiveIcon": { "foregroundImage": "./assets/icon.fg.png" } },
    "plugins": ["expo-router", "expo-secure-store"]
  }
}
```

EAS Build for CI:
```bash
npm install -g eas-cli
eas login
eas build:configure   # creates eas.json
eas build --platform all --profile production
```

## Gotchas
- `expo-modules-core` must match the Expo SDK version exactly; mixing versions causes native crashes
- `npx expo start` uses Metro bundler; clear cache with `--clear` flag when module resolution breaks
- Managed workflow can't use arbitrary native modules — use `expo-modules` or eject early
- `app.config.ts` (dynamic) takes precedence over `app.json`; don't maintain both
- EAS build machines don't have your local keystore; configure credentials with `eas credentials`
- `runtimeVersion` policy must be consistent across all OTA update channels or updates won't apply

## Related
- `react-native-over-the-air-updates.md`
- `react-native-new-architecture.md`
- `ios-app-store-submission.md`
- `android-play-store-submission.md`

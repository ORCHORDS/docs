# android-play-store-submission

**Issue:** Preparing and submitting an Android app to Google Play Store
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Play Store submission requires a signed AAB (Android App Bundle), compliance with policy on permissions and target SDK, and correct Play Console configuration. Common blockers: unsigned builds, wrong targetSdk, missing privacy policy.

## Pattern / Solution
**Build a signed AAB:**
```bash
# EAS Build (recommended)
eas build --platform android --profile production

# Manual (Gradle)
cd android
./gradlew bundleRelease
# Output: android/app/build/outputs/bundle/release/app-release.aab
```

**Keystore (create once, store safely):**
```bash
keytool -genkey -v -keystore my-release-key.jks \
  -alias my-key-alias -keyalg RSA -keysize 2048 -validity 10000
```

```groovy
// android/app/build.gradle
android {
    signingConfigs {
        release {
            storeFile file(MYAPP_STORE_FILE)
            storePassword MYAPP_STORE_PASSWORD
            keyAlias MYAPP_KEY_ALIAS
            keyPassword MYAPP_KEY_PASSWORD
        }
    }
    buildTypes {
        release { signingConfig signingConfigs.release }
    }
}
```

**Play Console requirements:**
- Target SDK: must be within 1 year of current Android release (currently API 34+)
- 64-bit support: all AABs must include arm64-v8a
- App signing: enroll in Google Play App Signing (Google manages the final signing key)
- Internal test → Closed testing → Open testing → Production (staged rollout)

**EAS Submit:**
```bash
eas submit --platform android --latest \
  --track production \
  --key /path/to/service-account.json
```

## Gotchas
- Once you enroll in Google Play App Signing, you can never retrieve the signing key — this is intentional
- `versionCode` must increase with every upload; it cannot be reused
- `targetSdkVersion` below the minimum causes rejection without explanation in the policy violation email
- Dangerous permissions (READ_CONTACTS, RECORD_AUDIO) require a privacy policy URL and justification in the console
- Play Store reviews can take several days for first submissions; updates are typically reviewed in hours
- APKs are no longer accepted for new apps; only AABs

## Related
- `react-native-expo-setup.md`
- `android-firebase-messaging.md`
- `android-keystore-biometrics.md`

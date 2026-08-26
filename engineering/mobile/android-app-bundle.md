# android-app-bundle

**Issue:** Publishing Android apps as AAB (Android App Bundle) to reduce download size via Play Feature Delivery
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
APKs include resources for all screen densities and languages; AABs let Google Play generate device-specific APKs, reducing download size by 15–35%.

## Pattern / Solution
Build an AAB instead of APK:
```sh
# Gradle
./gradlew bundleRelease

# Output: app/build/outputs/bundle/release/app-release.aab
```

Sign with `jarsigner` or Gradle signing config:
```groovy
android {
  signingConfigs {
    release {
      storeFile file(System.getenv("KEYSTORE_PATH"))
      storePassword System.getenv("KEYSTORE_PASSWORD")
      keyAlias System.getenv("KEY_ALIAS")
      keyPassword System.getenv("KEY_PASSWORD")
    }
  }
  buildTypes {
    release { signingConfig signingConfigs.release }
  }
}
```

Dynamic feature module (on-demand download):
```groovy
// Dynamic feature module build.gradle
plugins { id 'com.android.dynamic-feature' }
android {
  dynamicFeatures = [":feature_scanner"]
}
```

```kotlin
// Install on demand
val splitInstallManager = SplitInstallManagerFactory.create(context)
val request = SplitInstallRequest.newBuilder()
  .addModule("feature_scanner")
  .build()
splitInstallManager.startInstall(request)
```

## Gotchas
- Google Play is the only APK generator for AABs; sideloading requires `bundletool` to extract APK sets
- Enable Play App Signing in the Play Console — Google re-signs the APK after optimizing; keep your upload key separate
- Dynamic features add latency at first use; show a loading indicator during module installation
- `adb install` does not accept AAB files; use `bundletool build-apks` + `bundletool install-apks` for local testing

## Related
- `mobile-app-size-optimization.md`
- `mobile-ci-cd-fastlane.md`
- `mobile-obfuscation-proguard.md`

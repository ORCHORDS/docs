# mobile-obfuscation-proguard

**Issue:** Configuring R8/ProGuard obfuscation for Android apps to protect code and reduce size
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
R8 shrinks, obfuscates, and optimizes release builds but breaks apps that use reflection, serialization, or certain SDKs without proper keep rules.

## Pattern / Solution
`proguard-rules.pro`:
```proguard
# Keep model classes used with Gson/Moshi (reflection-based)
-keep class com.example.myapp.model.** { *; }

# Keep Retrofit interfaces
-keep,allowobfuscation interface com.example.myapp.api.** { *; }

# Keep enums (accessed by name)
-keepclassmembers enum * {
    public static **[] values();
    public static ** valueOf(java.lang.String);
}

# Firebase Crashlytics — keep crash reporting symbols
-keepattributes SourceFile,LineNumberTable
-keep public class * extends java.lang.Exception

# OkHttp
-dontwarn okhttp3.**
-keep class okhttp3.** { *; }

# Parcelables
-keep class * implements android.os.Parcelable {
    public static final android.os.Parcelable$Creator *;
}
```

Verify the build:
```sh
./gradlew assembleRelease
java -jar retrace.jar app/build/outputs/mapping/release/mapping.txt crash.txt
```

## Gotchas
- Always store `mapping.txt` from each release build — it's required for crash symbolication
- R8 is more aggressive than ProGuard; test release builds before submitting to the Play Store
- Adding `-dontobfuscate` defeats the security purpose; use specific `-keep` rules instead
- Third-party SDKs ship with their own consumer ProGuard rules via `consumerProguardFiles` — these are applied automatically

## Related
- `android-app-bundle.md`
- `mobile-crash-symbolication.md`
- `mobile-app-size-optimization.md`

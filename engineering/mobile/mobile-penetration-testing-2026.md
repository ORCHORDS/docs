# mobile-penetration-testing-2026

**Issue:** Running a credible mobile app penetration test against iOS and Android builds in 2026, including the new SDK/runtime constraints
**Date:** 2026-08-12
**Status:** documented

## Symptom / Context
Your app ships (or is about to ship) and you need to verify it resists the OWASP MASVS
(Mobile Application Security Verification Standard) controls before submission or as part
of a compliance audit. The 2026 landscape adds: Apple's Xcode 26 / iOS 26 SDK mandate,
tightened iOS privacy controls, Android 15/16 changes, and new store rules around SDK
disclosure. A test that passed in 2024 may now be invalid.

## Pattern / Solution

**Scope first (MASVS L1 vs L2 vs R):**
- L1 — baseline security (most consumer apps).
- L2 — high-assurance (fintech, health, identity).
- R — resilience against reverse-engineering (banking, DRM).
Pick the level with stakeholders; testing for R when you only need L1 burns budget.

**Static analysis (before touching a device):**
```bash
# iOS — unpack the IPA, scan the Mach-O binary
unzip app.ipa -d ipa_extracted
otool -L ipa_extracted/Payload/App.app/App          # linked frameworks
class-dump-z ipa_extracted/Payload/App.app/App > classes.txt  # Obj-C symbols
# Swift symbols: use swift-demangle on `nm` output

# Android — decode the APK/AAB
apktool d app.apk -o app_decoded                     # manifest + smali
jadx-g app.apk                                       # decompiled Java/Kotlin
mobscan --apk app.apk                                # MASVS-aware scanner
```

**Dynamic instrumentation:**
```bash
# Android — Frida on a rooted device or emulator
frida -U -f com.example.app -l hook.js --no-pause
# Bypass SSL pinning for traffic capture
frida -U -f com.example.app -l universal-android-ssl-pinning-bypass.js

# iOS — requires a jailbroken device on iOS < current (26.x jailbreaks lag by months)
# For current iOS, use a repackaged IPA with Frida gadget injected via resigning
```

**Network analysis:**
- Set up mitmproxy or Burp Suite as the device's HTTP proxy.
- For pinned apps, test with the pinning bypass FIRST; confirm the app even makes the
  request before declaring "traffic is encrypted."
- Check WebSocket, gRPC, and QUIC — many apps pin only HTTPS and leak over these.

**Runtime checks to confirm:**
- Tapjacking / overlay protection (Android `filterTouchesWhenObscured`).
- Clipboard access in background (Android 15 blocks it; verify your target min SDK).
- Screenshot flag on sensitive screens (`FLAG_SECURE` Android, blurred `UIScreen` iOS).
- Background snapshot masking on iOS (the app switcher should show a placeholder).

**Report by MASVS control, not by finding:**
Map every issue to a MASVS / OWASP MSTG ID. Compliance reviewers speak that vocabulary.

## Gotchas
- iOS 26 SDK builds cannot be class-dumped cleanly if Swift is used heavily — symbols are
  stripped by default. Request an unstripped build or a dSYM from the dev team for the test.
- Apple requires Xcode 26 builds as of April 28, 2026. Older IPAs in your archive are not
  representative; always test the current submission build.
- Modern Android apps ship with Play Asset Delivery / feature modules split out of the
  base APK. A standalone APK from `apktool` will be missing code; request the full AAB
  and use `bundletool` to build per-device APKs.
- Frida detection is now standard in banking/health apps. Your bypass hook must run before
  the app's `Application.onCreate`; otherwise the app exits before you attach.
- Jailbreak/root detection false negatives: emulators (Genymotion, Android Studio AVD)
  are detected trivially by production apps. Use a real rooted device or resign the IPA.
- Certificate pinning via `Network Security Config` (Android) and `Info.plist` ATS (iOS)
  is the default in 2026 templates — "no pinning" findings are increasingly rare; check
  pinning on your backend-issued dynamic pins, not just the static ones.
- Screenshot tests of the app switcher are mandatory evidence for L1 control V7.3 —
  testers skip this and it's a real, common finding.
- OWASP MASVS v2 (current as of 2026) renamed several controls; reports citing v1.x IDs
  will be rejected by some reviewers. Always cite the current version.
- Pen-test a debug build AND a release build. Debug builds often disable root detection
  and may show different (worse) behavior; only the release build is representative.

## Related
- `mobile-obfuscation-proguard.md`
- `jailbreak-root-detection.md`
- `certificate-pinning.md`
- `android-network-security-config.md`
- `ios-app-transport-security.md`
- `cross-platform-app-attestation-device-integrity.md`

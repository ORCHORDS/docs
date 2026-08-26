# App Size Optimization and Bundle Analysis — iOS and Android

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your iOS app is 180 MB and your Android APK is 120 MB. App Store
analytics show a 15% drop in install conversion compared to last year,
correlating with app size growth. Users in emerging markets on limited
data plans abandon downloads mid-way. Your team added three SDK
dependencies last quarter without checking their size impact — one
analytics SDK alone added 25 MB of native libraries. Nobody knows
which assets or frameworks contribute most to the final binary.

## Context

App size is a critical KPI in 2026: for every 6 MB increase in app
size, install conversion rates drop approximately 1%. Optimization
spans three layers — code (tree shaking, dead code elimination),
assets (image compression, format modernization), and delivery
(platform-specific thinning and dynamic delivery). Both Apple and
Google provide mechanisms to deliver only the resources a specific
device needs, but developers must actively configure them. As of 2026,
all new apps on Google Play must use AAB (Android App Bundle) format.

## iOS app thinning

```
Three components:

Slicing:
  → App Store generates device-specific builds
  → Delivers only matching resources (@2x for non-Pro, arm64 only)
  → Requires asset catalogs for images (not loose files)

Bitcode:
  → Deprecated in Xcode 14+, no longer relevant

On-Demand Resources (ODR):
  → Tag resources with keywords, App Store hosts them
  → App requests tag groups at runtime
```

```swift
// On-Demand Resources — request assets when needed
let request = NSBundleResourceRequest(tags: ["level-5-assets"])
request.beginAccessingResources { error in
    if let error = error {
        // Handle download failure
        return
    }
    // Resources now available locally
    let image = UIImage(named: "level5-background")
}

// Release resources when no longer needed
request.endAccessingResources()
```

## Android App Bundle and dynamic delivery

```kotlin
// Dynamic Feature Modules — deliver features on-demand
val request = SplitInstallRequest.newBuilder()
    .addModule("camera_feature")
    .build()

splitInstallManager.startInstall(request)
    .addOnSuccessListener { sessionId ->
        // Module downloading
    }
    .addOnFailureListener { exception ->
        // Handle failure
    }

// Monitor download progress
splitInstallManager.registerListener { state ->
    when (state.status()) {
        SplitInstallSessionStatus.INSTALLED -> {
            // Module ready to use
        }
        SplitInstallSessionStatus.DOWNLOADING -> {
            val progress = state.bytesDownloaded() * 100 /
                state.totalBytesToDownload()
        }
    }
}
```

```
AAB benefits over APK:
  → Google Play generates optimized APKs per device
  → Splits by: screen density, CPU architecture, language
  → Typical savings: 20-40% smaller downloads
  → Required for all new Google Play apps (2026)
```

## Asset optimization

```
Image formats (savings vs PNG):
  WebP:   30-70% smaller, broad mobile support
  AVIF:   50-80% smaller, limited mobile OS support
  SVG:    Variable, ideal for icons and simple graphics

Checklist:
  → Convert PNG/JPEG to WebP for raster images
  → Use SVG for icons and simple vector graphics
  → Remove unused density variants (@1x if min target is @2x)
  → Font subsetting: include only used glyphs (70-90% savings)
  → Audio: Opus codec (50% smaller than MP3)
  → Video: HEVC or AV1 over H.264

Tree shaking and dead code:
  → Android: R8/ProGuard eliminates unused Java/Kotlin code
  → iOS: Swift compiler dead-code stripping (release builds)
  → React Native: --release enables minification + tree shaking
  → Flutter: flutter build --release (AOT + tree shaking)
  → Requires ES Module imports (CommonJS blocks tree shaking)
  → Typical savings: 20-50% of bundle size
```

## Bundle analysis tools

```
Platform        Tool                          Purpose
──────────────────────────────────────────────────────────────
iOS             Xcode App Thinning Report     Per-device size breakdown
Android         Android Studio APK Analyzer   Category breakdown (dex, res, native)
React Native    react-native-bundle-visualizer  Treemap of JS bundle
Flutter         flutter build --analyze-size    Size by package
Cross-platform  Emerge Tools                  Automated size regression in CI
Cross-platform  Bitrise Size Analyzer         Upload IPA/APK/AAB for analysis

CI integration:
  → Track app size per build (fail if delta > threshold)
  → Compare size against previous release
  → Alert on new dependencies that add > 5 MB
```

## Anti-patterns

- **Including unused SDKs** — third-party SDKs pull in far more code
  than expected. Audit every dependency's size contribution before
  adding it. Remove SDKs that are no longer used.
- **Shipping universal binaries** — include only the architectures
  your users need. Shipping x86_64 for an iOS-only app wastes space.
  Use AAB on Android to let Play generate arch-specific APKs.
- **Not using asset catalogs (iOS)** — without asset catalogs,
  slicing cannot remove unused density variants. All @1x/@2x/@3x
  assets ship to every device.
- **Not tracking size in CI** — without automated regression
  detection, size creeps up unnoticed. Integrate size tracking into
  your build pipeline.

## Gotchas

- **CommonJS imports block tree shaking** — a single `require()` in
  a dependency chain can prevent the bundler from eliminating unused
  exports. Prefer ESM-compatible libraries.
- **ProGuard/R8 over-stripping** — aggressive minification can
  remove classes used via reflection. Maintain proper keep rules for
  reflection-based code (serialization, DI frameworks).
- **Download size vs install size** — the App Store and Play Store
  show download size (compressed), but install size is larger.
  Users see install size on their device storage. Optimize both.
- **Dynamic feature module cold start** — features loaded via dynamic
  delivery have a download delay on first use. Show progress UI
  and handle offline scenarios gracefully.

## Verification

- App uses asset catalogs (iOS) and AAB format (Android).
- Images are WebP or SVG where appropriate.
- Bundle analysis runs in CI with size regression alerts.
- Unused SDKs and dependencies are removed.
- Tree shaking is enabled for release builds.
- Dynamic delivery is configured for optional features.

## Related

- `documentation/categories/mobile/app-store-review-guidelines-compliance.md`
- `documentation/categories/mobile/react-native-new-architecture-fabric-jsi.md`
- `documentation/categories/performance/critical-rendering-path-css-optimization.md`

## Source URLs (verified 2026-08-16)

- Mobile App Size Optimization: Development Process — https://dev.to/merbayerp/mobile-app-size-optimization-the-burden-of-the-development-process-kgo
- 10 Tips to Reduce iOS & Android App Size — https://www.zeepalm.com/blog/10-tips-to-reduce-ios-and-android-app-size
- Android App Bundle vs APK: What Changed — https://trysonar.app/blog/android-app-bundle-vs-apk
- Flutter Tree Shaking & Bundle Optimization: Advanced Guide — https://www.technaureus.com/blog-detail/flutter-tree-shaking-and-bundle-optimization-guide

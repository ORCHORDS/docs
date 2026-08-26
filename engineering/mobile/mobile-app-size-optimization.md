# mobile-app-size-optimization

**Issue:** Reducing iOS and Android app binary size to improve conversion rates and pass store size limits
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Apps over 200 MB cannot be downloaded over cellular by default on iOS; large Android APKs correlate with lower install rates.

## Pattern / Solution
**Android:**
```groovy
android {
  buildTypes {
    release {
      minifyEnabled true          // enable R8 shrinking
      shrinkResources true        // remove unused resources
      proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
    }
  }
  // Split APKs by ABI (not needed if using AAB)
  splits {
    abi { enable true; reset(); include 'arm64-v8a', 'x86_64'; universalApk false }
  }
}
```

Analyze size with: `./gradlew analyzeReleaseBundle` or upload AAB to Play Console for detailed breakdown.

**iOS:**
- Enable Bitcode (or use `LLVM_LTO = YES` for link-time optimization)
- Use `xcrun simctl` + `assetutil` to find large unused assets
- Compress images with `pngcrush` or `imageoptim`

**React Native:**
```sh
# Check bundle size
npx react-native bundle --platform android --entry-file index.js --bundle-output /tmp/bundle.js
wc -c /tmp/bundle.js
```

- Use `metro-bundle-analyzer` to find large dependencies
- Replace heavy libraries (`moment` → `date-fns`, `lodash` → specific imports)
- Lazy-load rarely used screens via dynamic imports

## Gotchas
- `shrinkResources` only removes resources unreachable from code; unused assets kept by `keep.xml` rules still bloat the app
- Large font files in `assets/` are not tree-shaken; embed only required weights/scripts
- On iOS, App Thinning generates per-device assets; track "download size" not "install size"
- `minifyEnabled` without proper ProGuard rules breaks reflection-based libraries

## Related
- `android-app-bundle.md`
- `mobile-obfuscation-proguard.md`
- `mobile-battery-optimization.md`

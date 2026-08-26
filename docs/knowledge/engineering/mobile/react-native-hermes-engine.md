# react-native-hermes-engine

**Issue:** Understanding and configuring the Hermes JavaScript engine in React Native
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Hermes is Meta's JavaScript engine optimized for React Native — it AOT-compiles JS to bytecode, reducing startup time and memory. It is the default engine since RN 0.70 but requires knowing its limitations.

## Pattern / Solution
**Verify Hermes is active:**
```ts
import { HermesInternal } from 'global';
const isHermes = () => !!HermesInternal;
console.log('Running on Hermes:', isHermes());
```

**Enable in older RN (< 0.70):**
```kotlin
// android/app/build.gradle
project.ext.react = [enableHermes: true]
```

```ruby
# ios/Podfile
:hermes_enabled => true
```

**Hermes bytecode compilation:**
```bash
# Pre-compile for release (EAS does this automatically)
npx react-native bundle --platform android --dev false --entry-file index.js --bundle-output android/app/src/main/assets/index.android.bundle
```

**Source maps for crash symbolication:**
```bash
# Generate source map alongside bundle
npx react-native bundle ... --sourcemap-output sourcemap.json
# Upload to Sentry / Bugsnag
npx sentry-cli react-native appcenter MyApp android sourcemap.json
```

**Hermes inspector (DevTools):**
```
chrome://inspect → Configure... → localhost:8081
```

## Gotchas
- Hermes does not support all V8/JSC APIs; `Proxy` and some `Reflect` methods had limited support pre-RN 0.73
- Source maps must be uploaded to your crash reporter or stack traces are unreadable in production
- Hermes bytecode is version-specific; a bundle compiled for Hermes 0.12 won't run on 0.11
- `Date.toLocaleString()` behavior differs from JSC — use `Intl` APIs explicitly or the `@formatjs/intl` polyfill
- Profiling in Hermes uses a sampling profiler, not the V8 timeline — the format differs from what Chrome DevTools expects natively

## Related
- `react-native-performance-optimization.md`
- `react-native-new-architecture.md`
- `mobile-crash-reporting.md`

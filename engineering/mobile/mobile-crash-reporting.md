# mobile-crash-reporting

**Issue:** Capturing and symbolizing crash reports from production mobile apps
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Production crashes are hard to debug without symbolized stack traces. Crash reporters automatically capture, group, and symbolize crashes. Without source maps / dSYMs uploaded, stack traces are unreadable.

## Pattern / Solution
**Sentry (React Native):**
```bash
npx expo install @sentry/react-native
npx sentry-wizard -i reactNative
```

```ts
import * as Sentry from '@sentry/react-native';

Sentry.init({
  dsn: 'https://xxx@sentry.io/yyy',
  environment: __DEV__ ? 'development' : 'production',
  tracesSampleRate: 0.2, // 20% of sessions for performance
  enableAutoSessionTracking: true,
  attachScreenshot: true, // capture screenshot on crash
  beforeSend: (event) => {
    // Strip PII
    if (event.user) delete event.user.email;
    return event;
  },
});

// Wrap root component
export default Sentry.wrap(App);
```

**Capture errors manually:**
```ts
try {
  await riskyOperation();
} catch (error) {
  Sentry.captureException(error, {
    tags: { screen: 'checkout', action: 'payment' },
    extra: { orderId: order.id },
  });
}
```

**Upload source maps (EAS):**
```bash
# Add to eas.json postBuild hook
npx sentry-expo-upload-sourcemaps dist/
```

**Upload dSYMs (iOS):**
```bash
# Automatically after Xcode Archive
sentry-cli upload-dif --org my-org --project my-app \
  ~/Library/Developer/Xcode/DerivedData/**/dSYMs/
```

**Upload ProGuard mappings (Android):**
```groovy
// android/app/build.gradle
apply plugin: 'io.sentry.android.gradle'
sentry { uploadNativeSymbols = true; includeNativeSources = true }
```

## Gotchas
- Source maps must match the exact build — regenerate and re-upload for every release
- Sentry groups crashes by stack trace; a single unhandled promise rejection at the root inflates one issue with unrelated crashes
- `beforeSend` returning `null` drops the event; use it for test environments or noisy errors you choose to ignore
- Hermes stack traces without source maps show bytecode offsets — unreadable; source map upload is not optional
- Error boundaries in React do not catch async errors or errors in event handlers; those go to the global handler

## Related
- `react-native-hermes-engine.md`
- `mobile-performance-profiling.md`
- `mobile-analytics-patterns.md`
- `react-native-testing-patterns.md`

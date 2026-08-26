# capacitor-webview-to-native-migration

**Issue:** Deciding when to move a feature from the web view (HTML/JS) to a native Capacitor plugin, and how to do it without breaking the existing UI
**Date:** 2026-08-12
**Status:** documented

## Symptom / Context
Your Capacitor app started as a wrapped web app and worked well, but now certain screens
feel janky, gestures don't match the platform, or a feature (background work, biometric
prompt, native list virtualization) cannot be expressed in the web view. You need a
repeatable rule for what stays in the web view versus what becomes native.

## Pattern / Solution

**Decision matrix — move to native when ANY of these are true:**
| Signal | Why |
|---|---|
| 60fps scroll/fling required | Web view compositing drops frames on long lists |
| Platform gesture (iOS edge swipe back, Android predictive back) | Web cannot participate |
| Background task beyond a few seconds | OS suspends the web view; need WorkManager / BGTaskScheduler |
| Native UI element (Contacts picker, share sheet, permission sheet) | Web polyfills look wrong |
| Sensitive credential access | Native Keystore/Keychain only |
| File larger than ~50 MB | Web blob handling OOMs on low-end Android |

If none apply, **keep it in the web view** — premature native migration doubles your
maintenance surface for no user-visible benefit.

**Migration pattern —渐进 (progressive) replacement:**

1. Identify the single component (not the whole screen) that needs native.
2. Write a Capacitor plugin exposing only that component's API (see
   `capacitor-native-bridge-plugin-development.md`).
3. For full-screen native views, present them over the web view and pop back:
```kotlin
// Android — launch a native Activity from a plugin method
@PluginMethod
fun openNativeScanner(call: PluginCall) {
    val intent = Intent(this.context, NativeScannerActivity::class.java)
    startActivityForResult(call, intent, "scannerResult")
}
```
```swift
// iOS — present a native UIViewController
@objc func openNativeScanner(_ call: CAPPluginCall) {
    DispatchQueue.main.async {
        let vc = NativeScannerViewController()
        vc.onComplete = { result in call.resolve(["code": result]) }
        self.bridge?.viewController?.present(vc, animated: true)
    }
}
```
4. Keep the web view's state intact across the present/dismiss — Capacitor suspends JS
   but does not destroy it; verify your component rehydrates on `resume`.
5. Ship behind a feature flag so you can A/B test native-vs-web and roll back.

**Performance validation:**
- Measure with the platform profiler before declaring victory. Web view @ 45fps that
  becomes native @ 60fps is a win; web view @ 58fps becoming native @ 60fps is not worth it.
- Watch cold-start time: each new native Activity/ViewController adds to launch cost if
  initialized eagerly. Lazy-load plugins with `@CapacitorPlugin` keepalive = false.

## Gotchas
- A native screen presented over the web view does NOT inherit your web app's theming.
  Duplicate your design tokens (colors, spacing, typography) into native resources or the
  screen will look like a different app.
- iOS requires `present(_:animated:)` on the main thread from the bridge's
  `viewController`. Calling it from a background queue silently fails.
- Android `startActivityForResult` inside a Capacitor plugin needs the `@ActivityCallback`
  annotation on the result method, or the callback is never invoked.
- Returning a large payload (image bytes, big JSON) from native to JS marshals through
  the Cordova-style bridge and is slow on Android. Write to a file and return a path, or
  use Capacitor's Blob/File support.
- Web view state is lost on `configurationChange` (rotation) unless you handle it. Native
  screens rotate cleanly; mixed apps need to test both orientations.
- The HTML `<input type="file">` and `<input type="camera">` work in the web view but
  bypass your native permission UX. Migrate these to a native plugin for consistent
  permission prompts and to control compression.
- Capacitor's `pause`/`resume` events are throttled. Long native flows (>30s) may see the
  web view's timers paused; use a heartbeat from native, not a JS `setInterval`.
- Don't migrate the entire navigation stack to native — Capacitor's web view is a single
  Activity/ViewController. Native-per-screen hybrid (a la React Native's old architecture)
  is not supported and produces jarring transitions.

## Related
- `capacitor-native-bridge-plugin-development.md`
- `webview-security.md`
- `mobile-app-size-optimization.md`
- `mobile-performance-profiling.md`
- `react-native-webview-patterns.md`

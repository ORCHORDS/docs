# mobile-app-lifecycle-process-death

**Issue:** Cross-platform mobile teams routinely treat "the app is running" as a stable assumption, but both Android and iOS can kill an app's process at any time while it is backgrounded, then relaunch it cold when the user returns — losing all in-memory state (navigation stack, form input, scroll position, tokens in RAM). Users experience this as "the app forgot where I was" and give it one-star "loses my draft" reviews. This article covers how the Android and iOS lifecycles actually behave in 2025-2026, how to persist state so relaunch is seamless, and how to test process death deliberately instead of discovering it in production.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How the two operating systems actually kill your app

1. **Android process death is scheduled by the OS, not requested.** When memory pressure rises, Android's low-memory killer destroys backgrounded processes (lowest priority first) with no callbacks — `onDestroy()` is not guaranteed to run. Anything not persisted in `onSaveInstanceState()` / `SavedStateHandle` before the app is backgrounded is gone.
2. **Android configuration changes are the cheap rehearsal.** Rotation, dark-mode toggles, locale changes, and window resizing recreate the Activity by default, exercising the same save/restore path as process death. Apps that survive rotation but not process death usually have state captured in `onCreate` conditionals that skip restore.
3. **User-initiated kills restore nothing on Android.** Swiping the app away from Recents or force-stopping it clears the saved-instance-state Bundle by design; the next launch is a fresh start and the system sets `isTaskRoot` with an empty savedInstanceState. Never build a UX that depends on state surviving a user swipe.
4. **iOS suspends rather than kills, then jettisons under pressure.** After `sceneDidEnterBackground` the app is frozen in memory; the OS may later terminate it silently (jetsam). On relaunch, only state you persisted yourself — `SceneStorage`, `NSUserActivity`, files — comes back. iOS gives roughly seconds to save during backgrounding, so writes must be synchronous and small.
5. **Don't rely on `willSave`-style last-moment callbacks.** Both platforms reserve the right to kill a suspended/frozen process without further notice. Persist incrementally at meaningful checkpoints (draft saved on every keystroke debounce, navigation persisted on route change), not in a single shutdown hook.

## Persisting state that survives (Android)

1. **`SavedStateHandle` in ViewModels.** Inject it into Jetpack Compose / ViewModel state holders for small, serializable UI state (selected tab, search query, form fields). It survives both configuration changes and process death, and unlike `onSaveInstanceState` Bundles it is available before the first frame.
2. **Keep it small and primitive.** Saved state is serialized into a Bundle with a practical ~1 MB transaction limit; blowing it crashes with `TransactionTooLargeException` on some OEM builds. Store IDs and primitives, not objects — persist `selectedItemId: Long`, not the whole item JSON.
3. **Room / DataStore for anything structural.** Durable data (draft documents, queued uploads, cached feed pages) belongs in Room or DataStore, not in saved state. Pattern: `SavedStateHandle` holds a `draftId`, the ViewModel loads the draft from Room on init.
4. **Navigation state belongs to the navigation library.** Navigation Compose serializes the back stack per-destination into saved state automatically, but only if every route argument is a primitive or `Parcelable` with defaults. Custom objects on the back stack silently break restoration.
5. **Test it deterministically.** `adb shell am kill <package>` while backgrounded (API 23+) kills the process exactly like the OS would; there is no emulator equivalent of "wait for memory pressure." Add a debug menu action that calls it so QA can verify restore on every screen.

## Persisting state that survives (iOS)

1. **`@SceneStorage` for view state.** SwiftUI's per-scene property wrapper writes small values (selected tab, draft text) to state restoration storage on backgrounding and transparently restores on relaunch. Same size discipline as Android: strings, numbers, raw values — not model objects.
2. **`NSUserActivity` for "what was the user doing."** Publish an activity with a payload (document ID, cursor position, search query) when the scene backgrounds and restore it in `scene(_:willConnectTo:)` / `onContinueUserActivity`. Handoff and Spotlight deep links reuse the same mechanism, so you get state restoration and continuity in one API.
3. **Respect the three `scenePhase` states and their limits.** `.inactive` fires for control-center pulls and partial overlays — do not treat it as "going away." Only `.background` is a save point. SwiftUI has no equivalent of `sceneDidDisconnect`, so multi-window iPad apps bridging UIKit need `UISceneDelegate` callbacks for teardown.
4. **Write synchronously before returning from background.** `sceneDidEnterBackground` gives a short, non-guaranteed window; the reliable pattern is to keep a continuously-updated small snapshot file or update `SceneStorage`/activity as state changes, then just flush tiny deltas on background.
5. **Encrypt anything sensitive you persist.** State-restoration storage and snapshot files sit on disk unprotected unless you mark them `NSFileProtectionComplete` — drafts, tokens, and message text restored from an unencrypted snapshot are a classic pentest finding (see `mobile-penetration-testing-2026.md`).

## Testing and hardening checklist

1. **Add process death to the QA script for every feature.** The example project mobile test protocol (logcat running, screenshots at each transition) should include: navigate to screen, enter data, Home, `adb shell am kill` (Android) or relaunch after Simulator "Simulate memory warning" (Xcode > Device > Simulate Memory Warning), then reopen and screenshot the restored state.
2. **Test on the cheapest supported device.** Low-RAM devices (and Android Go editions) kill background processes far more aggressively than flagships; a Samsung S22 test device will almost never reproduce what a 2 GB device does daily. Use an Android Go emulator profile or `adb shell cmd activity make-uid-idle` to force standby behavior.
3. **Restore tokens before UI, not during rendering.** Session restore must happen in the launch path (Android `ViewModel` init / `Application`; iOS app initializer), because the first frame usually gates on auth state. Avoid restoring from network on the critical path — hydrate from disk, refresh in background.
4. **Handle the "partial restore" class of bugs.** The most common production symptom is state restored but side effects missing: drafts restored but attachments pointers dead, list position restored but the list itself now empty. Every persisted ID needs a plan for when its referent is gone (re-fetch, drop gracefully, show placeholder).
5. **Instrument restore in analytics.** Log a `state_restored` event with elapsed time and which keys were present; a spike in cold launches with empty restores after a release is the earliest signal that a migration or serialization change silently broke restoration.

## Related

- `android-viewmodel-patterns.md` — where `SavedStateHandle` plugs in
- `mobile-jwt-storage-pitfalls.md` — session/token restore on cold launch
- `android-foreground-service-restrictions.md` — work that continues after the UI process dies
- `mobile-e2e-testing.md` — automating the kill-and-relaunch flow

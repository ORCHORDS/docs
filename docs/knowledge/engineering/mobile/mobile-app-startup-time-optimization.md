# mobile-app-startup-time-optimization

**Issue:** App startup time is the first performance signal users and both stores judge: Play's Android Vitals flags apps whose cold startup exceeds thresholds (slow-start classes starting at 5 s) and downgrades their store visibility, while Apple surfaces App Launch percentiles in Xcode Organizer and via reviews ("so slow to open"). Cold start regressions accumulate silently — every new SDK, init hook, and splash-screen dependency adds milliseconds until launch takes seconds. This article covers how to measure TTID/TTFD and pre-main/post-main time honestly on both platforms in 2025-2026, the highest-leverage fixes (Baseline/Startup Profiles on Android, dylib and initializer hygiene on iOS), and how to stop regressions with automated benchmarks.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Measure honestly before optimizing

1. **Know your two Android metrics: TTID and TTFD.** Time-to-Initial-Display (first frame) is reported automatically, but it's a vanity metric — Time-to-Fully-Drawn is when content is actually usable. Call `Activity.reportFullyDrawn()` (or `ComponentActivity.reportFullyDrawn` / Compose's `ReportDrawnWhen`) when your real content is interactive; Play Vitals and Macrobenchmark both key off it.
2. **Get a quick local number with `adb shell am start -W`.** It prints `TotalTime` (TTID) and `WaitTime` for a launch; run 5-10 times on a physical midrange device after `adb shell am force-stop` and take the median. This is the cheapest regression smoke test — but it cannot see TTFD or in-app blockers, which Macrobenchmark handles.
3. **Use Macrobenchmark for real Android numbers.** `StartupTimingMetric` from the androidx benchmark library gives cold/warm/hot startup distributions on rooted or profileable devices; FrameTimingMetric catches jank in the first scroll. Gains from profiles sometimes show only in `FrameTimingMetric` — measure both before concluding "no improvement."
4. **Read iOS launch phases, not one number.** Instruments' App Launch template (and MetricKit `MXAppLaunchMetric`) split launch into pre-main (dyld mapping, relocations, static initializers) and post-main (application/scene init, first frame). Xcode Organizer > Metrics > App Launch shows real-user P50-P95 percentiles; optimize for the tail (P90+ on old devices), not the median.
5. **Baseline against real-user data, not lab heroes.** Play Console > Vitals > App startup times shows the user distribution and the slow/very-slow thresholds your visibility depends on; Organizer percentiles do the same for iOS. If P95 real users are 4 s and your lab shows 900 ms, the gap (old devices, cold caches, network on launch) is the actual problem.

## Highest-leverage Android fixes

1. **Ship Baseline Profiles.** The `baselineprofile` Gradle plugin generates profiles via Macrobenchmark that tell the platform which classes to AOT-compile at install; production case studies in 2025 report roughly 20-30% startup improvements (Duolingo ~30%, Meta documented fleet-wide gains). Profiles cover critical user journeys beyond startup, improving first-scroll jank too.
2. **Add Startup Profiles and regenerate both as code changes.** Startup Profiles (a separate, startup-focused artifact merged via the Gradle plugin) further cut dex/class setup on cold start; Meta's 2025 post stresses that profiles go stale as the app grows — schedule regeneration in CI on release branches, not once ever. A stale profile silently reverts you to JIT performance.
3. **Audit `Application.onCreate` and ContentProviders.** Every third-party SDK init (analytics, crash, ads) on the main thread serializes before your first frame; many register hidden `ContentProvider` initializers that run before `Application` entirely. Use the App Startup library (`androidx.startup`) or `InitializerProvider` to order/lazy them, and move anything not needed for first frame to a background dispatcher or `androidx.startup` deferred init.
4. **Cut splash-screen costs and windowBackground tricks.** Use `androidx.core.splashscreen` (correct themed icon, bounded `setKeepOnScreenCondition`), never a network-gated splash, and don't use opaque window backgrounds to hide slow inflation — it just converts white screen into "frozen splash," which users perceive identically (and ANR-watchdog timers start regardless).
5. **Slim the class graph and dependency set.** Startup cost scales with classes touched: enable R8 full mode, drop unused SDKs (each adds registrar/proguard surface), prefer lazy DI graph construction (Hilt `Lazy<T>`), and check with Macrobenchmark's method traces which libraries dominate. For WebView-shelled apps (Capacitor), native-side startup is small but WebView first-paint is the real clock — see `capacitor-webview-to-native-migration.md`.

## Highest-leverage iOS fixes

1. **Fix pre-main first: fewer dylibs, no `+load`.** Every dynamic framework costs dyld mapping/rebinding at launch; merge or static-link rarely-used frameworks (Xcode 16's static-linking defaults help), eliminate `+load` and C++ static initializers, and audit with Instruments' dyld instrumentation. Mergeable libraries and `-ObjC` link hygiene pay off before touching app code.
2. **Defer everything not needed for the first frame.** Move SDK inits, IAP observers, and logging setup off the critical path (background queue or `SceneDelegate` post-first-frame); Apple's canonical guidance (WWDC "Optimizing App Launch") is to prioritize work by what the user actually sees first.
3. **Instrument with `os_signpost` and guard with XCTest metrics.** Wrap launch phases in signposts (`os_signpost("launch")` intervals) to get in-app stage timing in Instruments; Xcode's launch-time XCTest metrics build and relaunch repeatedly for stable averages — wire these into CI as a regression gate (see `mobile-testing-jest.md`-adjacent native test patterns and `useyourloaf`'s approach of asserting a target duration).
4. **Don't block on disk/network before UI.** Keychain reads, `UserDefaults` mass loads, and token-refresh-on-launch are classic P95 killers; hydrate from last-known-good cached state synchronously (small) and refresh async — the same "restore from disk, refresh in background" rule as `mobile-app-lifecycle-process-death.md`.
5. **Watch size and first-launch effects.** App thinning aside, larger binaries pay slower dyld/page-in costs on old devices; `mobile-app-size-optimization.md` covers trimming. Also measure *update-time* first launches (no warm caches) — that's the distribution Organizer shows spiking after every release.

## Preventing regressions

1. **Benchmark in CI on a fixed device class.** Run Macrobenchmark startup suites (Android) and launch XCTest metrics (iOS) nightly on pinned hardware/emulator profiles; fail the build when median cold TTID or TTFD regresses >5-10%. Record traces as CI artifacts so a failure comes with its flame graph.
2. **Track TTFD as a product metric.** Add a `fully_drawn` analytics event with elapsed time and launch type (cold/warm), segmented by device tier; watch the P95 weekly. Play Vitals and MetricKit give you platform truth, but in-app events attribute delays to your screens (deep-link targets vs home).
3. **Review init-order changes like API changes.** A one-line SDK addition in `Application`/`AppDelegate` is the most common silent regression; keep an explicit, commented init manifest listing what initializes on the main thread and why, so code review has a diffable contract.
4. **Test cold starts after process death, not just fresh installs.** First-launch numbers (no caches) differ from steady-state cold launches; both differ from warm. Your CI matrix should cover at least cold (post-force-stop) and warm; use `adb shell am kill` / Simulator relaunch to hit the process-death path (see `mobile-app-lifecycle-process-death.md`).
5. **Re-verify profile effectiveness after upgrades.** AGP/Kotlin/Compose upgrades change code paths and can invalidate or even regress profile gains (community reports exist of profiles appearing to hurt after toolchain changes). Re-run Macrobenchmark comparisons on every toolchain bump and keep a no-profile variant to diff against.

## Related

- `mobile-performance-profiling.md` — general profiling tooling (this article is launch-specific)
- `mobile-app-size-optimization.md` — download size and its launch-time side effects
- `mobile-ci-cd-github-actions.md` — wiring benchmark gates into pipelines
- `react-native-performance-optimization.md` — RN-specific startup (bridge/Hermes) concerns

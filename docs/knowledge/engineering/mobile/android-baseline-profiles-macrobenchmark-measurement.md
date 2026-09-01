# Baseline Profile Generation and Macrobenchmark Measurement

Baseline profiles precompile hot code paths so ART skips just-in-time interpretation on first run. This article covers generating profiles with a Macrobenchmark module, packaging them through ProfileInstaller, and measuring the improvement without fooling yourself with warm-cache numbers.

## Scope

A baseline profile is a list of classes and methods (in ART's HRF human-readable profile syntax) that the platform compiles ahead of time during a background `BackgroundDexOptService` pass after install or update. Without one, a fresh install runs fully interpreted until the runtime learns the hot paths itself, which is why cold start and first-scroll are disproportionately slow on new installs. The scope here is Android-first-party tooling: the `baselineprofile` Gradle plugin, Macrobenchmark as the profile producer, and `ProfileInstaller` as the delivery mechanism. It does not cover Cloud Profiles alone, Jetpack Compose compiler metrics, or startup profiles for library authors beyond what an app team consumes.

## Workflow or implementation guidance

Set up three Gradle modules: `:app`, `:benchmark` (com.android.test with `androidx.benchmark` Macrobenchmark plugin), and typically a `:baselineprofile` producer module using the `androidx.baselineprofile` plugin. The plugin wiring declares the app module under test, and the profile task traces the app while a scripted scenario exercises the paths you want compiled.

1. Author the producer as a `@Test`-style class with `MacrobenchmarkRule`. Each method is a scenario: cold startup via `StartupMode.COLD`, then a scroll through the primary list using `actionOn_scroll` gesture helpers. Include navigation into the two or three screens that dominate real usage, not just the launcher.
2. Configure `CompilationMode` explicitly. For profile generation the rule runs the default full-compile skip; for measuring improvement you need three runs in one report: `CompilationMode.None()` (simulates a fresh install with no profile), `CompilationMode.Partial(baselineProfile = true, fromStartup = true)` (profile applied), and optionally `CompilationMode.Full()` as the theoretical ceiling.
3. Generate with `./gradlew :app:generateBaselineProfile` from a rooted API 33+ emulator or a physical device (release build type, `Benchmark` or signed release variant). The task outputs `baseline-prof.txt` into each source set the plugin targets, including any library modules that expose profiled code.
4. Verify packaging: the merged `assets/dexopt/baseline.prof` (compiled form) must appear inside the APK/AAB. `ProfileInstaller` in the app's runtime dependencies schedules the profile copy after install; on API 33+ the platform's `ArtServiceLogging`/cloud profile path can also apply it at install time via Play.
5. Measure with `./gradlew :benchmark:connectedCheck`. Read the Studio output or the HTML report; the key metric pair is `timeToInitialDisplayMs` (TTID) and `timeToFullDisplayUs`/`TTFD` when you report fully with `SimulationMetadata`. Assert nothing in CI; treat thresholds as alerting, since device variance is high.

Scenario quality dominates everything else. A profile generated from a stub screen compiles the wrong methods and can measure slightly negative against `None()` when compile time overhead outweighs interpretation savings.

## Controls

- Pin the profile-producing device: use the same rooted emulator image (for example, a `google_apis` non-Play image with `adb root` available) for every regeneration; profiles from different devices vary in rules-inclusion noise.
- Regenerate after meaningful app changes: navigation rewrites, DI graph changes, or a big Compose migration shift hot paths; a stale profile decays toward no-op.
- Keep startup filters and startup profiles separate where the tooling offers it (startup profile enables faster class loading at startup in addition to the baseline profile).
- Exclude nothing manually unless a profiler shows a pathological entry; hand-editing `baseline-prof.txt` is a maintenance trap.
- Run `benchmark` generation on release-type builds; debug builds inflate cold start with checks that never exist in production and poison the profile.
- Gate release notes / dashboards on the delta between `None()` and `Partial`, not the absolute number; the delta is stable across devices in a way raw TTID is not.

## Validation evidence

A valid measurement looks like this, from a representative run: `CompilationMode.None()` cold TTID 620 ms, `Partial(baselineProfile = true)` 430 ms, `Full()` 400 ms - roughly 30 percent improvement, with the profile run closing most of the gap to full compilation. Confirm the profile actually shipped by pulling the APK and checking `assets/dexopt/baseline.prof` is non-trivially sized, and inspect the device state with `adb shell dumpsys package <pkg> | grep -i profile` or `pm compile` subcommands to see compilation status. Re-run the A/B comparison after each regeneration. Evidence for this article's procedures: Android documents baseline profile creation and Macrobenchmark `CompilationMode` semantics in the references below, and the Gradle task names come from the `androidx.baselineprofile` plugin documentation.

## Failure modes and correction

- Profile generation silently produces an empty or near-empty `baseline-prof.txt`: the producer scenarios never left the idle screen, or the app crashed on launch in the benchmark variant. Fix the scenario; verify the file has thousands of lines for a real app.
- No measured improvement: check that `ProfileInstaller` is on the runtime classpath and that measurement uses `CompilationMode.Partial`, and confirm the test installs the profiled build rather than a cached build with different signatures.
- CI flakiness in the benchmark numbers: cold-start timing on shared emulators is noisy. Use `StartupMode.COLD` with the emulator's snapshot disabled, discard warmups via `metrics` warmup iterations, and compare medians across a fixed device profile.
- `generateBaselineProfile` fails on a Play-image emulator: `adb root` is unavailable. Switch to a non-Play `google_apis` image or a rooted physical device.
- First launch after store update still slow: store-applied profiles depend on Play and OS version; `ProfileInstaller`'s delayed install can land minutes after update. This is expected - measure `None()` versus `Partial()` in Macrobenchmark, which applies the profile synchronously, to isolate app-side issues.

## Limitations

Baseline profiles improve code-compilation readiness only; I/O, network, main-thread disk reads, and oversized dependency graphs are untouched and frequently dominate cold start. Profile generation requires supported device/emulator images and rooted access. Numbers from Macrobenchmark on an emulator are directionally useful but not representative of a mid-tier phone fleet. Cloud profiles may supplement or override app-shipped profiles depending on Play and OS behavior, so measured gains in the lab can differ from field gains.

## Canonical sources

- Android Developers - "Baseline profiles overview": https://developer.android.com/topic/performance/baselineprofiles/overview (verified HTTP 200)
- Android Developers - "DEX layout optimizations and baseline profiles": https://developer.android.com/topic/performance/baselineprofiles/dex-layout-optimizations (verified HTTP 200)
- Android Developers - Jetpack Benchmark release notes (Macrobenchmark and baselineprofile plugin versions): https://developer.android.com/jetpack/androidx/releases/benchmark (verified HTTP 200)

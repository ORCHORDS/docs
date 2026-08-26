# mobile-memory-leak-detection

**Issue:** Memory leaks almost never present as leaks. They present as OOM crashes attributed by crash reporters to random innocuous lines (because the killer strikes wherever allocation finally fails), as weird lag from growing GC pauses on Android, or as the iOS Jetsam kill with no stack at all. By the time crash-free rate dips, the leak has been shipping for weeks. On iOS the dominant cause is reference cycles (closures capturing self, delegates held strongly, timers never invalidated); on Android it is context and view references outliving their components, listeners registered on long-lived singletons, and static references accumulating. This article covers the toolchain on each platform, the recurring leak shapes, and how to stop regressions in CI.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why leaks surface as OOM crashes

1. **Jetsam and LMK kill without a crash stack.** iOS terminates the app for exceeding its memory footprint, and crash SDKs can only log the termination after the fact, so the report blames whatever code was running. Treat rising "out of memory" or EXC_RESOURCE reports as a leak investigation, not as an allocation-site bug at the reported line.
2. **Growth is invisible until it is fatal.** A screen leaking 2 MB per visit survives testing (nobody opens a detail screen 200 times) and dies in production on a heavy user with a small device. Memory dashboards per screen class are how you see the slope before the cliff.
3. **Low-RAM devices are the canary.** Crashes concentrate on the oldest supported hardware. Segmenting memory metrics by device model tells you in days what aggregate dashboards hide for months.

## iOS tooling

1. **Xcode Memory Graph Debugger is the primary weapon.** Pause the app, press Debug Memory Graph, and Xcode snapshots all live objects with their references; simple retain cycles are auto-flagged with a purple warning in the debug navigator. DoorDash's engineering writeup documents exactly this workflow for finding cycles at scale: search your class name in the graph, walk the reference chain, and identify the strong edge that should be weak.
2. **Instruments Leaks and Allocations for trends.** The Leaks template catches C-level and Objective-C cycles the graph misses; Allocations with generation markers (take a snapshot, navigate to a screen and back, take another) shows whether instances of a class return to baseline or accumulate per navigation cycle.
3. **Guard against the classic Swift cycles.** Closures capturing self strongly (fix with weak self capture lists), non-weak delegates, NotificationCenter observers never removed, Timer holding the target, and Combine/async task cancellables stored nowhere so they outlive the view. Each has a mechanical fix; audit them as a category, not one-off.
4. **Watch WKWebView and image pipelines.** WebViews retain large backing stores and are expensive to leak once; downsampled image loading (thumbnail-sized decode for list views) is the single biggest footprint fix in most image-heavy iOS apps.

## Android tooling

1. **LeakCanary in debug builds, always.** It hooks destroyed activities and fragments, dumps the heap when their references survive, and prints a human-readable leak trace automatically. The overwhelming majority of Android leaks a team will ever find are found by LeakCanary on a developer device in the first week.
2. **Android Studio Profiler heap dumps for the rest.** Capture a heap dump, filter by your class, and compare instance counts across navigation cycles; the reference chain view answers "what is holding this dead Activity."
3. **Audit the recurring shapes.** Static/singleton references to Context or View, listeners registered in onCreate but never unregistered, Handler inner classes implicitly holding the outer Activity, coroutine scopes tied to a longer-lived object than the screen, and bitmaps held at full resolution in caches. These categories cover nearly all field leaks.
4. **Consider strict mode and lint early.** StrictMode disk/network violations often coincide with memory smells, and Android lint flags some leak-prone patterns (unregistered receivers, static Contexts) before code review does.

## Declarative UI does not save you

1. **SwiftUI leaks through captured references.** Views are cheap structs, but closures passed into long-lived objects (observed stores, task blocks capturing a model) still retain graphs; the Memory Graph remains the arbiter, and onAppear/onDisappear asymmetry (subscribe in one, forget the other) builds unbounded subscription lists.
2. **Compose leaks via composition-scoped references.** remember ed state, listeners, and callbacks captured by objects that outlive the composition (an app-scope singleton holding a composable lambda) keep whole UI trees alive after the screen is gone; rememberUpdatedState and proper LaunchedEffect keys are the standard corrections.
3. **Recomposition bugs masquerade as leaks.** Unstable lambdas causing continuous recomposition burn memory in caches and look like growth in profiles; check stability annotations before hunting phantom references.

## Stopping regressions

1. **Automate the navigation-cycle check.** A UI test (or scripted monkey run in CI) that navigates to every screen and back N times, paired with LeakCanary on Android and a footprint assertion (or XCTest measuring block with memory metric on iOS), turns "we think it is fine" into a pass/fail gate per PR.
2. **Track memory metrics per release.** Harvest foreground memory footprint and low-memory warnings from field telemetry (MetricKit on iOS gives per-device memory pressure and diagnostic logs for free; on Android, use onTrimMemory callbacks and vitals dashboards) and alert on upward drift between versions.
3. **Fix leaks by category, not by instance.** When LeakCanary fires, fix the pattern everywhere it occurs (all listeners, all observers) rather than the single reported instance; the same author usually wrote the same bug in five places.
4. **Keep leak detection out of release builds.** LeakCanary's heap dumping and debug-only graph tooling are expensive; ship them in debug/internal builds only, and rely on field telemetry for production.

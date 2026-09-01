# Jetpack Compose Recomposition and Stability Diagnosis

Compose recomposition is the mechanism that keeps UI in sync with state; uncontrolled recomposition is the mechanism that makes lists jank and drains batteries. The failure signature is always the same: a composable runs far more times than its inputs change. This article covers how the compiler infers stability, how to read recomposition counts with tooling, and the concrete fixes in priority order.

## Scope

Covered: Compose compiler stability inference (stable / unstable / immutable), `@Stable` and `@Immutable` annotations, skippability and restartability of composables, `derivedStateOf`, key usage in lazy lists, and the Layout Inspector recomposition counts plus compiler-metrics output. Not covered: general Compose state-holding patterns in ViewModels or performance measurement with Macrobenchmark (see the baseline-profiles article in this family).

## Workflow or implementation guidance

**Understand the contract.** The Compose compiler classifies every type used as a composable parameter: primitives and `String` are stable; `val`-only data classes of stable types are stable; `List<T>`, `Map<K,V>`, and any class from a non-Compose-compiled module are unstable by default (the compiler cannot see their mutation surface). A composable whose parameters are all stable is *skippable* - when inputs are `equals`, recomposition of the whole function is skipped. One unstable parameter poisons skippability for the function and every parent that passes it, which is why a single unstable model class can cascade recomposition through a screen.

**Diagnose in this order.**

1. Generate compiler metrics: set the compiler arguments in the module build (`composeCompiler { reportsDestination = layout.buildDirectory.dir("compose_reports") }` with the Compose Compiler Gradle plugin for Kotlin 2.0+, or the older `freeCompilerArgs` flags `-P plugin:androidx.compose.compiler.plugins.kotlin:reportsDestination=...`) and build. Read `*-composables.txt` for restartable/skippable status per function and `*-classes.txt` for per-class stability and the reason ("unstable property repository" is a typical smoking gun).
2. Open Layout Inspector (Android Studio, Debug mode on a device or emulator running API 29+ for accurate counts), enable "Show recomposition counts" and "Show recomposition highlight". Interact with the screen naturally for 30 seconds. A list item recomposing hundreds of times during scroll indicates the parameter flow is unstable or the state is read too high in the tree.
3. Check state reads. Every `state.value` read inside a composable scopes recomposition to that composable. Hoisting reads upward (reading `scrollState.value` in a parent to decide a badge) forces the parent to re-run on every frame; `derivedStateOf { scrollState.value > threshold }` converts a frame-frequency read into a boolean that changes rarely and limits invalidation.

**Fix in priority order.**

- **Restructure state reads**: move `State<T>` parameters down to the innermost composable that needs them; pass lambdas (`() -> Unit`) instead of state values so parents do not re-run.
- **Make models immutable**: replace `var` with `val`, collections with immutable types. Either mark model classes `@Immutable` when guaranteed, or adopt immutable collection types (`kotlinx.collections.immutable.PersistentList` with the Compose compiler recognizing them) so the compiler can treat them as stable.
- **Stabilize with configuration, not blanket annotations**: a module compiled with the Compose compiler configured with a stability configuration file (`STABILITY_CONFIGURATION_FILE` path listing classes like `java.time.Instant` as stable) fixes third-party types without annotating code you do not own. Use `@Stable` on classes you maintain where the guarantee is real; a lying annotation produces incorrect skipping and stale UI.
- **Key lazy items**: `LazyColumn` without `key = { it.id }` rebuilds item state on data shifts and loses scroll position fidelity; keys make moves cheap and prevent full-item recomposition on reorder.
- **Use `remember` for computed intermediates** and `rememberSaveable` for UI state that must survive configuration change; do not recompute parses or allocations on every recomposition.
- **Defer reads for animation**: wrap `Modifier` values reading animatable state in `Modifier.drawBehind` or use `graphicsLayer` lambdas so per-frame value changes invalidate drawing only, not layout or composition.

## Controls

- Add compiler-metrics report generation to CI and fail on regressions: diff the count of non-skippable restartable composables in hot screens (feed, player, editor) between main and PR.
- Keep the Layout Inspector recomposition audit as a release-checklist step for any screen with lists or animation.
- Treat `@Immutable`/`@Stable` annotations as assertions with review scrutiny: require a comment stating the invariant when applied to classes with any mutable surface.
- Enforce lambda-passing style in lint (a custom Detekt/Lint rule flagging `State` parameters on public composables of large screens).
- Re-run the audit after dependency upgrades: a new library version can flip a class from stable to unstable with no code change in your app.

## Validation evidence

The canonical evidence pair: compiler report showing the target composable flips from "restartable, not skippable" to "restartable, skippable", and Layout Inspector counts before/after on the same interaction script (for example item rows: 214 recompositions down to 9 during a 30-second scroll). The compiler metrics files list each unstable parameter name, which should match exactly the parameter you fixed. For regression safety, an instrumented test using `Modifier.debugInspectorInfo`-style counting or the `TestMonotonicFrameClock` verifies that emitting the same input twice does not re-run a skippable composable body (test via a side-effect counter in the composable).

## Failure modes and correction

- "Annotated @Immutable but UI shows stale data": the class actually mutates (a `var`, or a mutable list held elsewhere); the annotation disabled correctness. Remove the annotation, restore immutability, re-annotate.
- Recomposition counts stay high after making models immutable: state is still read too high. Trace which parameter changed via the inspector's highlight; usually a `State<Boolean>` read in a top bar that toggles per scroll frame.
- Compiler metrics empty under Kotlin 2.x: the old `composeOptions.kotlinCompilerExtensionVersion` free-compiler-arg approach moved to the Compose Compiler Gradle plugin; reconfigure reports with the plugin DSL.
- Unstable types from a multi-module graph: a `:core:model` module without the Compose compiler plugin still gets inferred, but third-party AARs never do; use the stability configuration file for those.
- Performance did not improve despite skippable functions: the bottleneck is layout or draw, not composition. Move to Macrobenchmark frame-timing categories before more stability work.

## Limitations

Recomposition skipping is a composition-phase optimization; it cannot fix inefficient layout measure passes, overdraw, or main-thread I/O. Stability inference results vary with compiler and Kotlin versions, and metrics are a build artifact, not a runtime contract. Layout Inspector counts require debuggable builds on API 29+ and perturb timing; they indicate direction, not field performance.

## Canonical sources

- Android Developers - "Compose performance: stability": https://developer.android.com/develop/ui/compose/performance/stability (verified HTTP 200)
- Android Developers - "Compose lifecycle: recomposition and skipping": https://developer.android.com/develop/ui/compose/lifecycle (verified HTTP 200)
- Android Developers - Compose testing and inspection tooling: https://developer.android.com/develop/ui/compose/testing (verified HTTP 200)

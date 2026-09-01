# R8 Full Mode Shrinker Optimizations for Release Builds

R8 is Android's shrinker/optimizer/obfuscator: it shrinks (removes unused code), optimizes (inlines, merges, rewrites), and obfuscates (renames) your release bytecode in one pass. Full mode — the aggressive default since AGP 8 — makes stronger assumptions: it treats missing-keep-rule reflections as removable, strips default interface methods, and removes the implicit leniency of the old compat mode. Full mode produces smaller, faster builds and, correspondingly, more spectacular runtime crashes when a reflection path wasn't kept. This article covers what full mode changes, how keep-rule strategy must adapt, and the release-validation discipline that catches over-aggressive stripping before users do.

## Scope

This article addresses R8 in full mode for Android release builds: the differences from compat mode (removal of default-interface-method backports, stricter class merging, stronger vertical class merging, assumption-based optimization), keep-rule design (`-keep` versus `-keepnames`, allows vs. requires, `assertrules` family and `-keepattributes`), mapping files and deobfuscation, and validation strategy. It does not cover baseline profiles, multidex, or Jetifier/dependency migration.

## Workflow or implementation guidance

Full mode changes the contract in three ways that matter:

1. **Stricter removal defaults.** In compat mode, R8 kept some classes/methods that lacked keep rules as a safety net for reflection-heavy libraries. Full mode removes them. Any library that reaches your code reflectively (serialization frameworks, dependency injection, ORM annotations processors) must now be explicitly kept — the responsibility moved from R8's leniency to your rules.
2. **Default interface methods and horizontal/vertical class merging.** Full mode merges classes when provably safe, which breaks assumptions baked into older libraries (some service loaders, DI graphs walking class names). Symptoms appear as `ClassNotFoundException`/`NoSuchMethodException` at runtime on code paths the release build stripped or merged.
3. **Optimization assumptions.** `assumevalues`/`assume` rules and library-model-based optimizations can now eliminate branches the old mode kept. If your code branches on reflection-adjacent conditions or values the optimizer believes constant, full mode may fold them away.

The keep-rule strategy that survives full mode:

1. **Prefer `-keepnames` for debugging, `-keep` for genuine reflection.** `-keep` prevents both removal and renaming; `-keepnames` only prevents renaming of things that are otherwise kept. Rules that over-keep (blanket `-keep class com.foo.** { *; }`) recreate the bloat R8 exists to remove — full mode's win evaporates. Target rules at the reflective surfaces: entry points listed by each library's official consumer rules.
2. **Consume library-provided rules instead of hand-writing them.** Modern libraries ship consumer R8 rules inside their AARs (`META-INF/proguard`/`META-INF/com.android.tools/r8`), applied automatically. Hand-copied rules drift from library versions; the shipped rules track them. When a library has no rules, add minimal targeted keeps with a comment naming the library version and the reflective surface it protects — reviewable, upgradable.
3. **Keep what the platform reflects into:** `View` subclasses referenced from XML (`-keep public class * extends android.view.View { public <init>(android.content.Context); … }`), enum `values`/`valueOf` when serialized, `Parcelable` CREATORs, `Native`-bound methods (JNI needs stable names: keep classes with `native` methods and their names), serialization models (Gson/Moshi annotated types keep fields; annotations like `@JsonClass` are handled by generated adapters — keep only what the framework's docs demand).
4. **`-keepattributes` for the tooling you run.** `LineNumberTable` + `SourceFile` for readable stack traces (kept default); `*Annotation*` if runtime annotation processing; `Signature` for generics-reflection paths; `InnerClasses`/`EnclosingMethod` for anything walking class structure. Full mode under compat kept more of these implicitly.
5. **Mapping files are release artifacts.** R8 emits `mapping.txt` translating obfuscated names back. Upload to Play Console (deobfuscated crash reporting), archive per release with the AAB. Losing the mapping makes field crashes undebuggable — treat mapping retention as part of the release pipeline, not an afterthought.

Validation discipline — the actual defense against full-mode regressions:

- **Release-build smoke tests in CI, not just debug.** Run the app's core journeys against the minified release variant (`assembleRelease` + connected tests or a recorded-UI suite). Debug-variant testing hides every shrinker issue by construction; this is the single highest-value control.
- **Reflection inventory.** Grep the codebase and dependencies for reflective APIs (`Class.forName`, `getDeclaredMethod`, JSON deserialization over reflection) and map each to a keep rule or a library's consumer rules; review the inventory when upgrading libraries — the reflective surface moves.
- **Diff the mapping between releases.** Unexpected whole-package disappearances in `mapping.txt` between versions reveal accidental stripping of features (an optimizer removing a never-instantiated-but-reflected entry point) before support tickets do.
- **Stack-trace replay check.** Take a caught exception in the release build, symbolicate with `mapping.txt` (ReTrace/`r8 retrace`), and verify it resolves to a real frame — validating that attributes + mapping are coherent for crash tooling.

A worked example: an app using a JSON library that reflects field names. After enabling full mode (AGP 8 migration), release builds crash parsing server responses: `ClassNotFound`/null-field symptoms on models. Root cause: the old compat mode's implicit keeps covered reflective field access; full mode stripped unused-looking model classes. Fix: add the library's consumer rules (or targeted `-keep class com.app.models.** { <fields>; }` with a version-pinned comment), add a release-variant deserialization test to CI. The size win stays (95% of the app still shrinks), the reflective seam is explicit, and the CI release suite now guards it forever.

Tuning specifics worth knowing: `-dontoptimize`/`-dontobfuscate` are escape hatches for isolating issues (is it shrinking or optimizing? turn one off), not shipping configurations. `android.enableR8.fullMode` explicitly toggles the mode where the AGP default needs overriding. Startup profiles and startup-keep rules interact with optimization ordering — keep rules for startup paths minimal and measured.

## Controls

- CI runs the release (minified) variant through a core-journey test suite on every release-candidate build; minified-build failures block release regardless of debug-variant green.
- Keep-rule files are reviewed like code: each rule carries a comment naming the protected surface and its source (library docs/version); orphan rules are deleted in the same PR that removes their library.
- Mapping files archived immutably per release (retention ≥ crash-reporting horizon) and uploaded to Play Console automatically.
- Reflection inventory (code + third-party list) reviewed at dependency-upgrade time; a checklist item asks "does this library reflect? are its consumer rules present?"
- Mapping-diff between consecutive releases reviewed in release sign-off, with whole-class disappearances requiring justification.

## Validation evidence

- R8 full-mode behavior changes (stricter defaults, default interface method handling, class-merging aggressiveness), keep-rule semantics (`-keep` vs `-keepnames`, requires/allows, keepattributes), mapping/retrace tooling, and the AGP default since 8.0 are documented in Google's Android Developers shrink, obfuscate, and optimize your app guide and the R8 project documentation.
- Library consumer-rule mechanisms (`META-INF/com.android.tools/r8`, legacy proguard metadata) are documented in the Android Gradle Plugin and library-publishing guidance.
- A reproducible validation on any project: build release with full mode; run the minified variant through the reflection-annotated journeys (serialization, DI graph construction); any `ClassNotFoundException`/`NoSuchMethodException` found is by definition a missing keep rule — then toggle compat mode and observe the same journeys passing, demonstrating precisely which surfaces relied on legacy leniency.

## Failure modes and correction

- **Release-only reflection crashes.** Symptom: `ClassNotFoundException` in production paths green in debug. Correct by targeted keeps + release-variant CI journeys.
- **JSON fields silently null.** Symptom: deserialization returns empty models (names obfuscated, no rule). Correct by keeping model fields or switching to code-gen adapters.
- **JNI breakage.** Symptom: `UnsatisfiedLinkError` on native call. Correct by keeping native-bearing classes and their names.
- **Undebuggable crashes.** Symptom: obfuscated stack traces with no mapping. Correct by mapping archival + upload automation.
- **Blanket keeps undoing full mode.** Symptom: APK size balloons after "fixing" crashes with `** { *; }`. Correct by surgical rules with comments and size-diff gates in CI.

## Limitations

- Shrinker behavior depends on library models R8 bundles; old/unusual libraries may need rules the library never shipped.
- Full mode's optimizations evolve per AGP/R8 version; a green build does not transfer across toolchain upgrades without re-running the release suite.
- Reflection through string-built class names can never be fully statically kept — keep those classes by name explicitly and test.
- Mapping-based deobfuscation covers names, not inlined frames, without additional tooling state (retrace with the matching R8 version).

## Canonical sources

- Google, Android Developers — Shrink, obfuscate, and optimize your app (R8, full mode, keep rules, mapping): https://developer.android.com/studio/build/shrink-code
- Google, Android Developers — Compare R8 and ProGuard behavior (full mode vs. compat mode differences): https://developer.android.com/build/shrink-code#r8-full-mode

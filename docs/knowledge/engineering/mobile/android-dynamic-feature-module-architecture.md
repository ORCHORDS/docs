# Dynamic Feature Module Architecture Within the App Bundle

Dynamic feature modules (DFMs) restructure an Android app into a base APK plus on-demand or conditional splits. This article covers the architecture decisions - module boundaries, dependency direction, classloader visibility, and manifest fusion - that determine whether a DFM split works or ships missing-class crashes. It complements the existing article on conditional/on-demand delivery by focusing on module design rather than the delivery state machine.

## Scope

Covered: `com.android.dynamic-feature` Gradle modules, the `dist:` manifest namespace (`dist:module`, `dist:onDemand`, `dist:instant`, `dist:conditions`), runtime module access through Play Core's `SplitCompat` and `SplitInstallManager`, and the interaction between DFMs and R8/code shrinking. Not covered: Play Feature Delivery install-state handling (see `android-play-feature-delivery-install-states.md`), instant-app entry-point design (see `android-instant-apps-url-installation.md`), or on-demand native library loading details beyond ABI splits.

## Workflow or implementation guidance

Design modules top-down from a capability map, not from a code-size table.

1. **Map capabilities to modules.** A DFM boundary must be a user-visible capability ("video editor", "AR viewer") with its own screens, DI subgraph, and resources. Size-driven carving ("move everything over 2 MB into a module") produces cyclic needs: base code wants feature classes at startup. The rule is dependency direction only: DFMs may depend on the base; the base must never reference DFM classes unconditionally.
2. **Set up Gradle wiring.** The app module declares `dynamicFeatures += setOf(":feature:editor")`; each DFM module uses the `com.android.dynamic-feature` plugin and declares `implementation(project(":app"))` so it can reach base classes. Base declares only interfaces. Keep module-level `build.gradle` `minSdk`/`targetSdk` in lockstep with the base; the bundle enforces it, and CI should assert it.
3. **Choose delivery per module** in the DFM's manifest: `<dist:module dist:title="@string/editor_title" dist:onDemand="true">` plus `<dist:fusing dist:include="true"/>` for devices on API < 21 where the split model does not apply and the module fuses into the base APK. Conditional modules add `<dist:conditions>` (country, device-feature, min-SDK) - remember fusing must be enabled for conditional modules to reach older devices.
4. **Bridge to runtime access.** Enable `SplitCompat.install(context)` (or `SplitCompat.installActivity` per-activity on older patterns) before inflating feature layouts/resources so the classloader and `Resources` pick up installed splits. Newer Play Core versions apply split contents automatically after install confirmation for subsequent launches, but code running in the same process post-install needs the explicit bridge.
5. **Protect entry points from shrinking.** R8 sees base-module code referencing feature classes only via reflection/`Class.forName` or interface dispatch. Annotate feature entry points with `@Keep` or add proguard keep rules scoped narrowly to the entry-point classes; verify with a bundle-configured R8 run, not a debug monolithic install.
6. **DI scoping.** With Hilt/Dagger, DFMs contribute `@InstallIn` components through aggregation only if the processor sees them; a DFM whose generated factories are stripped breaks at runtime when first opened. Keep feature components' entry classes in keep rules and test with a release, minified build.

Resources and assets fuse per-split: a DFM's `strings`, drawables, and assets are addressable after install via split resources once SplitCompat is active. Do not move shared resources into DFMs; duplicates bloat every split that references them.

## Controls

- Enforce dependency direction with a CI check (for example, a Gradle task asserting the app module has no `implementation(project(":feature:..."))` edges) - the compiler permits the reverse direction only because DFMs depend on app, so a mistake here is silent.
- Assert base-only integrity: run the app with no DFM installed in an emulator and walk primary navigation; any `ClassNotFound`/`Resources$NotFound` is a base violation.
- Pin `bundletool` in CI and run `java -jar bundletool.jar build-apks --mode=default --connected-device` style verification plus `validate` on every release candidate to catch manifest-fusion errors (`dist:` attributes malformed, missing `dist:title`, conflicting `dist:instant`).
- Keep per-DFM size budgets explicit (for example editor under 15 MB compressed) and fail the build on regression; the point of the split is a smaller base, and unmetered DFMs quietly reassemble a monolith.
- Test with `SplitInstallManager` deferred states - treat "module installed" as a capability flag persisted per device, not a global constant.

## Validation evidence

Validate on a real split install, not a monolithic debug APK: `./gradlew :app:bundleRelease`, then `java -jar bundletool.jar build-apks --bundle=app-release.aab --output=app.apks --mode=universal` is the wrong mode for DFM testing; instead use `bundletool install-apks` of a default-mode `.apks` on a device (base splits only), then install DFMs through the app's own Play Core path or `bundletool install-multiple`. Walk each feature with minification on (`isMinifyEnabled = true` plus R8 full mode) and confirm every deferred entry point loads. Evidence for this article's procedures: the Android App Bundle and bundletool documentation define split structure and the `dist:` manifest namespace; Play Core documentation defines `SplitCompat` installation requirements.

## Failure modes and correction

- `ClassNotFoundException` on first feature launch under release build: R8 stripped the entry point or the DI factory. Fix with narrowly scoped keep rules and re-verify with minified builds.
- Feature works after process restart but not in the same session: `SplitCompat` bridge missing or invoked after `super.onCreate()` inflation. Install it before the activity uses split resources.
- "Unable to find resource" for strings inside a DFM: resource was referenced from base, or SplitCompat not installed. Move the resource into base (if genuinely shared) or defer access until after install.
- Bundle fails validation with dist-attribute errors: malformed namespace - the DFM manifest must declare `xmlns:dist="http://schemas.android.com/apk/distribution"` and the `<dist:module>` block exactly as documented; copy from a working sample, not from memory.
- Monolithic debug builds hide every one of these failures - always run at least one release-bundle smoke pass per feature.

## Limitations

DFM splits only function through Play distribution; sideloaded monolithic APKs fuse everything and mask defects. Conditional delivery conditions are evaluated by Play at install/update time, so they behave like coarse distribution filters, not runtime feature flags. Module uninstall and deferred uninstall depend on Play and device conditions. Very small modules (under roughly 1 MB) may cost more in session overhead and update complexity than they save, since each release re-uploads all splits.

## Canonical sources

- Android Developers - "Dynamic delivery with feature modules" (Play Core and DFM overview): https://developer.android.com/guide/playcore/feature-delivery (verified HTTP 200)
- Android Developers - bundletool reference (build-apks modes, split validation): https://developer.android.com/tools/bundletool (verified HTTP 200)
- Android Developers - "Shrink, obfuscate, and optimize your app" (R8 keep-rule interaction with deferred class loading): https://developer.android.com/build/shrink-code (verified HTTP 200)

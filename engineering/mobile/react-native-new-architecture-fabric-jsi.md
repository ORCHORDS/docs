# React Native New Architecture — Fabric, TurboModules, and JSI

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your React Native app has noticeable jank when scrolling complex lists,
a 3-second cold start on mid-range Android devices, and lag when
calling native modules from JavaScript. Profiling shows the async JSON
bridge between JavaScript and native is the bottleneck — serializing
and deserializing every cross-boundary call adds latency and prevents
synchronous layout measurements. You are on React Native 0.74 and need
to migrate to the New Architecture to unblock React 18 features
(Suspense, concurrent rendering) and improve performance.

## Context

React Native's New Architecture replaces the asynchronous JSON bridge
with four connected components: JSI (JavaScript Interface), Fabric
(new renderer), TurboModules (new native module system), and Codegen
(type-safe interface generation). Since React Native 0.76 (late 2024),
the New Architecture is the default for new projects. In 2026, it is
stable and required for React 18 features. Production migrations show
43% faster cold starts, 39% faster rendering, and 26% lower memory
usage. Hermes is the default JavaScript engine on both iOS and Android,
providing ahead-of-time bytecode compilation and lower memory footprint
than JavaScriptCore.

## Architecture comparison

```
Old Architecture (Bridge):
  JS Thread ──JSON serialize──► Bridge ──JSON deserialize──► Native
  ← Async, batched, serialized communication →
  ← No synchronous calls possible →
  ← All native modules loaded at startup →

New Architecture (JSI):
  JS Thread ──direct C++ call──► Native (via JSI host objects)
  ← Synchronous when needed, no serialization →
  ← Lazy loading of modules →
  ← Shared C++ layer across platforms →
```

## Core components

```
JSI (JavaScript Interface):
  → C++ API replacing the JSON bridge
  → JavaScript can hold references to C++ objects
  → Synchronous function calls across boundary
  → No serialization overhead
  → Foundation for Fabric and TurboModules

Fabric (Renderer):
  → New rendering system built on JSI
  → C++ shadow tree (cross-platform layout)
  → Synchronous layout measurement
  → Enables React 18 features:
    - Concurrent rendering
    - Suspense
    - Automatic batching
    - useTransition / useDeferredValue
  → Priority-based rendering (urgent vs background)

TurboModules:
  → New native module system replacing NativeModules
  → Lazy loading: modules loaded on first use, not at startup
  → Type-safe: interfaces generated from specs via Codegen
  → Synchronous method support via JSI
  → Direct C++ bindings (no JSON serialization)

Codegen:
  → Generates type-safe C++ interfaces from JS/TS specs
  → Flow or TypeScript type definitions → native code
  → Compile-time type checking across JS/native boundary
  → Eliminates runtime type mismatches

Hermes (JS Engine):
  → Default engine on iOS and Android
  → Ahead-of-time bytecode compilation
  → Faster startup (no JIT compilation needed)
  → Lower memory usage than JavaScriptCore
  → Built-in Intl support (no polyfills needed)
```

## TurboModule specification

```typescript
// NativeCalculator.ts — TurboModule spec
import type { TurboModule } from 'react-native';
import { TurboModuleRegistry } from 'react-native';

export interface Spec extends TurboModule {
  // Synchronous method (returns immediately via JSI)
  add(a: number, b: number): number;

  // Asynchronous method (returns Promise)
  fetchData(url: string): Promise<string>;

  // Method with callback
  subscribe(callback: (value: string) => void): void;

  // Constants (evaluated once at module init)
  getConstants(): {
    platform: string;
    version: string;
  };
}

export default TurboModuleRegistry.getEnforcing<Spec>('Calculator');
```

```java
// Android implementation (Kotlin)
class CalculatorModule(reactContext: ReactApplicationContext) :
    NativeCalculatorSpec(reactContext) {

    override fun getName() = "Calculator"

    override fun add(a: Double, b: Double): Double = a + b

    override fun fetchData(url: String, promise: Promise) {
        thread {
            val result = httpClient.get(url).body
            promise.resolve(result)
        }
    }
}
```

## Fabric component

```typescript
// NativeVideoPlayer.ts — Fabric component spec
import type { ViewProps } from 'react-native';
import codegenNativeComponent from 'react-native/Libraries/Utilities/codegenNativeComponent';
import type {
  Float,
  Int32,
  DirectEventHandler,
} from 'react-native/Libraries/Types/CodegenTypes';

interface NativeProps extends ViewProps {
  src: string;
  autoplay?: boolean;
  volume?: Float;
  onProgress?: DirectEventHandler<
    Readonly<{ currentTime: Float; duration: Float }>
  >;
  onEnd?: DirectEventHandler<null>;
}

export default codegenNativeComponent<NativeProps>('VideoPlayer');
```

## Migration steps

```
1. Update React Native to 0.76+
   npx react-native upgrade

2. Enable New Architecture (if not default)
   // android/gradle.properties
   newArchEnabled=true

   // ios/Podfile
   ENV['RCT_NEW_ARCH_ENABLED'] = '1'

3. Update native modules to TurboModules
   → Write TypeScript specs (NativeXxx.ts)
   → Run Codegen: npx react-native codegen
   → Update native implementations to extend generated specs

4. Update native views to Fabric components
   → Write component specs with codegenNativeComponent
   → Update native view managers to implement generated interfaces

5. Test third-party libraries
   → Check library compatibility with New Architecture
   → Update or replace incompatible libraries
   → Use interop layer for libraries not yet migrated

6. Performance validation
   → Measure cold start time (target: >30% improvement)
   → Profile rendering performance (Fabric vs old renderer)
   → Test on low-end devices (Android)
```

## Anti-patterns

- **Keeping the old bridge alongside JSI** — maintaining backward
  compatibility by keeping bridge-based modules active. The old
  bridge adds startup overhead even when JSI modules are available.
  Migrate fully and remove bridge dependencies.
- **Synchronous native calls for heavy work** — using JSI's
  synchronous capability for CPU-intensive operations. This blocks
  the JS thread. Use synchronous calls only for lightweight
  operations (layout measurement, simple calculations). Heavy
  work should remain asynchronous.
- **Ignoring Codegen type specs** — writing TurboModules without
  proper TypeScript specs. Without Codegen, you lose compile-time
  type safety and the interface contract between JS and native
  becomes implicit and error-prone.
- **Not testing on low-end devices** — the New Architecture
  improves performance, but regressions from incorrect migration
  are most visible on low-end Android devices. Always test on
  representative low-end hardware.

## Gotchas

- **Third-party library compatibility** — not all libraries
  support the New Architecture in 2026. Check the React Native
  Directory compatibility filter. Libraries using the interop
  layer work but do not benefit from JSI performance improvements.
- **Hermes debugger differences** — Hermes uses its own debugger
  protocol, not Chrome DevTools Protocol directly. Use Flipper or
  the Hermes Chrome debugger extension. Some debugging workflows
  differ from JavaScriptCore.
- **Codegen build step** — Codegen adds a build step that
  generates C++ code from TypeScript specs. If specs change, the
  native project must rebuild. This can slow down development
  iteration. Use autolinking to minimize manual Codegen invocation.
- **Memory management across JSI boundary** — JSI objects are C++
  objects exposed to JavaScript. If JavaScript holds a reference
  to a large native object, it is not garbage collected until the
  JS reference is released. Be mindful of large object lifetimes.

## Verification

- App cold starts within target time (benchmark before/after).
- Scrolling performance shows no jank on 60fps target devices.
- All native modules migrated from Bridge to TurboModules.
- Codegen specs match native implementations (compile-time check).
- React 18 features (Suspense, concurrent rendering) work correctly.
- Low-end Android devices tested with representative workloads.

## Related

- `documentation/categories/mobile/react-native-expo-managed-workflow.md`
- `documentation/categories/mobile/app-store-review-guidelines-compliance.md`
- `documentation/categories/performance/edge-computing-serverless-cdn-patterns.md`

## Source URLs (verified 2026-08-16)

- React Native New Architecture 2026: JSI & Production Guide — https://softaims.com/blog/react-native-new-architecture-2026
- React Native New Architecture: JSI, Fabric and TurboModules Explained — https://impacttechlab.com/react-native-new-architecture-app-performance/
- React Native Architecture Explained (2026) — https://spacetotech.com/blog/react-native-architecture-explained
- React Native New Architecture Migration Guide (2026) — https://www.agilesoftlabs.com/blog/2026/03/react-native-new-architecture-migration

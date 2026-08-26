# react-native-new-architecture

**Issue:** Migrating to or using React Native's new architecture (JSI, Fabric, TurboModules)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The new architecture (stable since RN 0.74) replaces the asynchronous bridge with JSI (JavaScript Interface), enabling synchronous native calls. It includes Fabric (new renderer) and TurboModules (new native module system).

## Pattern / Solution
**Enable new architecture:**
```kotlin
// android/gradle.properties
newArchEnabled=true
```
```ruby
# ios/Podfile
ENV['RCT_NEW_ARCH_ENABLED'] = '1'
```

With Expo:
```json
// app.json
{ "expo": { "newArchEnabled": true } }
```

**Writing a TurboModule:**
```ts
// NativeCrypto.ts — JS spec
import type { TurboModule } from 'react-native';
import { TurboModuleRegistry } from 'react-native';

export interface Spec extends TurboModule {
  hash(input: string): Promise<string>;
}

export default TurboModuleRegistry.getEnforcing<Spec>('NativeCrypto');
```

**Fabric native component spec:**
```ts
// NativeMapViewNativeComponent.ts
import type { ViewProps } from 'react-native';
import { requireNativeComponent, type HostComponent } from 'react-native';

type NativeProps = ViewProps & { region: Region };
export default requireNativeComponent<NativeProps>('RNMapView') as HostComponent<NativeProps>;
```

**Check compatibility:**
- Use `react-native-compatibility-check` or check the library's GitHub for `New Architecture` support badge
- `react-native-community` maintained libraries are generally compatible

## Gotchas
- Old-architecture modules using the bridge (`RCTBridgeModule`) work in interop mode but must eventually be migrated
- Fabric changes the timing of layout effects; some animations that worked in old arch may need adjustment
- CodeGen (generating C++ glue code) runs during the build — ensure `@react-native/codegen` is in devDependencies
- Concurrent React features (Suspense, transitions) are only fully supported with Fabric
- Libraries that access `RCTBridge` directly will crash under the new architecture without an interop layer

## Related
- `react-native-hermes-engine.md`
- `react-native-performance-optimization.md`
- `react-native-expo-setup.md`

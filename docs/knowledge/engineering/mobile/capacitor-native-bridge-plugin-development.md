# capacitor-native-bridge-plugin-development

**Issue:** Writing and consuming custom Capacitor plugins to expose native iOS/Android APIs to a web codebase
**Date:** 2026-08-12
**Status:** documented

## Symptom / Context
You have a web codebase (React, Vue, Angular) wrapped in Capacitor and need a device
capability that no official `@capacitor/*` or community plugin provides — e.g. a vendor
SDK, a platform-specific sensor, or a native UI component. You must author a local
plugin and call it from TypeScript without leaving the web view.

## Pattern / Solution

**Scaffold a local plugin (Capacitor 6/7):**
```bash
npm init @capacitor/plugin@latest
# name: my-native-echo, class: MyNativeEcho, package: com.example.mynativeecho
```

**TypeScript interface (shared with web):**
```ts
// src/definitions.ts
import type { PluginListenerHandle } from '@capacitor/core';

export interface EchoOptions { value: string; }
export interface EchoResult { value: string; }

export interface MyNativeEchoPlugin {
  echo(options: EchoOptions): Promise<EchoResult>;
  addListener(
    'nativeEvent',
    listener: (data: { ts: number }) => void,
  ): Promise<PluginListenerHandle>;
}
```

**Android implementation (Kotlin):**
```kotlin
@CapacitorPlugin(name = "MyNativeEcho")
class MyNativeEchoPlugin : Plugin() {
    @PluginMethod
    fun echo(call: PluginCall) {
        val value = call.getString("value") ?: ""
        val ret = JSObject()
        ret.put("value", value)
        notifyListeners("nativeEvent", JSObject().put("ts", System.currentTimeMillis()))
        call.resolve(ret)
    }
}
```
Register in `MainActivity.onCreate`: `registerPlugin(MyNativeEchoPlugin())`.

**iOS implementation (Swift):**
```swift
@objc(MyNativeEchoPlugin)
class MyNativeEchoPlugin: CAPPlugin, CAPBridgedPlugin {
    let identifier = "MyNativeEchoPlugin"
    let jsName = "MyNativeEcho"
    let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "echo", returnType: CAPPluginReturnPromise)
    ]

    @objc func echo(_ call: CAPPluginCall) {
        let value = call.getString("value") ?? ""
        call.resolve(["value": value])
        notifyListeners("nativeEvent", data: ["ts": Date().timeIntervalSince1970])
    }
}
```
Register in `Podfile` / `MainPlugin.m` with `CAP_PLUGIN(MyNativeEchoPlugin, "MyNativeEcho")`.

**Web consumption:**
```ts
import { MyNativeEcho } from 'my-native-echo';
const { value } = await MyNativeEcho.echo({ value: 'hi' });
await MyNativeEcho.addListener('nativeEvent', e => console.log(e.ts));
```

## Gotchas
- Web view methods that touch the main thread must dispatch back; long native work
  blocks the JS thread and freezes the UI. Run heavy work off-main on both platforms.
- Plugin method names are case-sensitive and must match between TS, Kotlin `@PluginMethod`,
  and Swift `@objc` selectors — silent "undefined is not a function" is almost always a typo.
- `registerPlugin` on Android must happen in `MainActivity.onCreate`, not in `Application`.
  Doing it in `Application` works in debug and breaks in release builds.
- iOS plugins require the `@objc` attribute and explicit `CAP_PLUGIN` registration macro;
  forgetting the macro means the plugin loads but methods are unreachable from JS.
- Return only JSON-serializable values (`JSObject` / dictionaries). Custom classes,
  `Date` objects, and binary must be converted — passing them resolves to `null`.
- `notifyListeners` events are dropped if no JS listener is attached yet. Buffer the last
  event or have the web side subscribe before triggering the native call.
- Local plugins (not published to npm) must be added to the app's dependency list and
  re-synced with `npx cap sync` after every native code change, or the new code is ignored.

## Related
- `capacitor-webview-to-native-migration.md`
- `webview-security.md`
- `mobile-camera-permissions.md`
- `react-native-webview-patterns.md`

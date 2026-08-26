# Mobile Thermal State Adaptation

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Users playing music or recording video on your app for 10–15 minutes report sluggish scrolling,
dropped frames, and in extreme cases system-forced app suspensions on iOS (the "iPhone needs to
cool down" banner). Android users on mid-range devices see ANRs (Application Not Responding)
dialogs when the SoC reaches thermal throttling. You have no telemetry on when throttling starts
and no UI adaptation that degrades gracefully.

## Context

Modern mobile SoCs run sustained workloads only until the die temperature reaches a threshold,
after which the OS governor reduces clock speeds. This reduces CPU/GPU performance by 30–60 %
on a throttled device, causing visible jank even for workloads previously comfortable at 60 fps.

Both platforms expose thermal state APIs:
- **iOS 11+**: `ProcessInfo.thermalState` with four states: `nominal`, `fair`, `serious`, `critical`
- **Android 10+ (API 29)**: `PowerManager.addThermalStatusListener` with eight constants
  (e.g. `THERMAL_STATUS_LIGHT`, `THERMAL_STATUS_SEVERE`, `THERMAL_STATUS_SHUTDOWN`)

React Native exposes neither directly; you need a native module or a Turbo Module to bridge
the platform API. This article covers both a custom Turbo Module approach and a Reanimated
worklet-safe bridge.

---

## 1. iOS Turbo Module for Thermal State

Create a new Turbo Module that reads `ProcessInfo.thermalState` and emits events.

```swift
// ios/ThermalManager/ThermalManager.swift
import Foundation
import React

@objc(ThermalManager)
class ThermalManager: RCTEventEmitter {

    private var thermalObserver: NSObjectProtocol?

    override func supportedEvents() -> [String] {
        return ["ThermalStateChange"]
    }

    override func startObserving() {
        thermalObserver = NotificationCenter.default.addObserver(
            forName: ProcessInfo.thermalStateDidChangeNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.emitThermalState()
        }
        // Emit current state immediately so JS can initialise
        emitThermalState()
    }

    override func stopObserving() {
        if let observer = thermalObserver {
            NotificationCenter.default.removeObserver(observer)
        }
    }

    @objc(getCurrentState:reject:)
    func getCurrentState(
        resolve: @escaping RCTPromiseResolveBlock,
        reject: @escaping RCTPromiseRejectBlock
    ) {
        resolve(thermalStateName(ProcessInfo.processInfo.thermalState))
    }

    private func emitThermalState() {
        let state = thermalStateName(ProcessInfo.processInfo.thermalState)
        sendEvent(withName: "ThermalStateChange", body: ["state": state])
    }

    private func thermalStateName(_ state: ProcessInfo.ThermalState) -> String {
        switch state {
        case .nominal:  return "nominal"
        case .fair:     return "fair"
        case .serious:  return "serious"
        case .critical: return "critical"
        @unknown default: return "nominal"
        }
    }
}
```

```objc
// ios/ThermalManager/ThermalManager.m
#import <React/RCTBridgeModule.h>
#import <React/RCTEventEmitter.h>

@interface RCT_EXTERN_MODULE(ThermalManager, RCTEventEmitter)
RCT_EXTERN_METHOD(getCurrentState:(RCTPromiseResolveBlock)resolve
                  reject:(RCTPromiseRejectBlock)reject)
@end
```

---

## 2. Android Module for Thermal Status

```kotlin
// android/app/src/main/java/com/example-org/example-repo
package com.orchords

import android.os.PowerManager
import com.facebook.react.bridge.*
import com.facebook.react.modules.core.DeviceEventManagerModule

class ThermalManagerModule(reactContext: ReactApplicationContext) :
    ReactContextBaseJavaModule(reactContext), LifecycleEventListener {

    private val powerManager: PowerManager by lazy {
        reactContext.getSystemService(PowerManager::class.java)
    }

    private val thermalListener = PowerManager.OnThermalStatusChangedListener { status ->
        emitThermalStatus(status)
    }

    override fun getName() = "ThermalManager"

    @ReactMethod
    fun addListener(eventName: String) { /* required for RCTEventEmitter */ }

    @ReactMethod
    fun removeListeners(count: Int) { /* required for RCTEventEmitter */ }

    @ReactMethod
    fun getCurrentState(promise: Promise) {
        promise.resolve(thermalStatusName(powerManager.currentThermalStatus))
    }

    @ReactMethod
    fun startListening() {
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.Q) {
            powerManager.addThermalStatusListener(
                reactApplicationContext.mainExecutor,
                thermalListener
            )
        }
    }

    @ReactMethod
    fun stopListening() {
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.Q) {
            powerManager.removeThermalStatusListener(thermalListener)
        }
    }

    private fun emitThermalStatus(status: Int) {
        reactApplicationContext
            .getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java)
            .emit("ThermalStateChange", thermalStatusName(status))
    }

    private fun thermalStatusName(status: Int): String = when (status) {
        PowerManager.THERMAL_STATUS_NONE    -> "nominal"
        PowerManager.THERMAL_STATUS_LIGHT   -> "fair"
        PowerManager.THERMAL_STATUS_MODERATE -> "fair"
        PowerManager.THERMAL_STATUS_SEVERE  -> "serious"
        PowerManager.THERMAL_STATUS_CRITICAL -> "critical"
        PowerManager.THERMAL_STATUS_EMERGENCY -> "critical"
        PowerManager.THERMAL_STATUS_SHUTDOWN -> "critical"
        else -> "nominal"
    }
}
```

---

## 3. React Native Hook and Adaptation Strategy

```ts
// hooks/useThermalState.ts
import { useEffect, useState } from "react";
import { NativeEventEmitter, NativeModules, Platform } from "react-native";

export type ThermalState = "nominal" | "fair" | "serious" | "critical";

const { ThermalManager } = NativeModules;
const emitter = ThermalManager
    ? new NativeEventEmitter(ThermalManager)
    : null;

export function useThermalState(): ThermalState {
    const [state, setState] = useState<ThermalState>("nominal");

    useEffect(() => {
        if (!ThermalManager) return;

        // Seed initial state
        ThermalManager.getCurrentState().then(setState).catch(() => {});

        // Android: start listener explicitly
        if (Platform.OS === "android") {
            ThermalManager.startListening?.();
        }

        const sub = emitter?.addListener("ThermalStateChange", (payload) => {
            // iOS sends { state: string }, Android sends string directly
            const newState: ThermalState =
                typeof payload === "string" ? payload : payload?.state;
            setState(newState ?? "nominal");
        });

        return () => {
            sub?.remove();
            if (Platform.OS === "android") {
                ThermalManager.stopListening?.();
            }
        };
    }, []);

    return state;
}
```

Adaptation table:

| Thermal state | Adaptation |
|---|---|
| `nominal` | Full quality: 60 fps animations, 1080p preview, all effects |
| `fair` | Reduce frame processor rate, cap video to 720p |
| `serious` | Disable frame processors, pause background syncs, lower animation fidelity |
| `critical` | Stop all camera/audio workloads, show user notice, offer to pause session |

```tsx
// components/VideoEditor.tsx
import { useThermalState } from "@/hooks/useThermalState";

export function VideoEditor() {
    const thermal = useThermalState();
    const frameRate = thermal === "nominal" ? 60 : thermal === "fair" ? 30 : 15;
    const quality = thermal === "critical" ? "low" : thermal === "serious" ? "medium" : "high";

    return (
        <>
            {thermal === "critical" && (
                <ThermalWarningBanner onPause={handlePause} />
            )}
            <VideoPreview frameRate={frameRate} quality={quality} />
        </>
    );
}
```

---

## 4. Observability and Analytics

Send thermal events to your analytics pipeline so you can correlate with crash/ANR rates:

```ts
// hooks/useThermalState.ts (extended)
import { track } from "@/analytics";

emitter?.addListener("ThermalStateChange", (payload) => {
    const newState: ThermalState =
        typeof payload === "string" ? payload : payload?.state;

    if (newState !== state) {
        track("thermal_state_change", {
            from: state,
            to: newState,
            screen: currentRoute(),
            session_duration_s: Math.round((Date.now() - sessionStart) / 1000),
        });
    }
    setState(newState ?? "nominal");
});
```

Dashboard query (Cloudflare Analytics Engine):

```sql
SELECT
  toStartOfHour(timestamp) AS hour,
  blob2 AS to_state,
  COUNT() AS transitions
FROM thermal_events
WHERE timestamp > NOW() - INTERVAL '7' DAY
GROUP BY hour, to_state
ORDER BY hour DESC, transitions DESC
```

---

## Anti-patterns

- **Ignoring thermal state and letting the OS decide** — iOS suspends foreground apps at
  `critical` without warning, resulting in data loss if the user is mid-edit. Gracefully pause
  and save state at `serious`.
- **Polling `ProcessInfo.thermalState` on a timer** — the notification fires within 50 ms of
  a change; polling adds CPU pressure that itself contributes to heating.
- **Reducing frame rate without informing the user** — unexpected quality drops feel like bugs.
  Show a subtle badge ("Device is warm — quality reduced") so users know it is intentional.
- **Applying the same adaptation on all device tiers** — a `serious` state on iPhone 15 Pro
  (still above 30 fps sustainable) is comparable to `fair` on iPhone XR. Consider pairing
  thermal state with device tier detection for finer adaptation.
- **Not testing on physical devices** — the iOS Simulator never enters `serious` or `critical`;
  Android emulators do not implement thermal APIs. Load test on real hardware under a blanket
  or in a warm environment to reproduce sustained throttling.

---

## Gotchas

- **iOS critical state app termination** — at `critical`, iOS may terminate background apps
  immediately. Your app will not be notified; use `UIApplication.willTerminateNotification` to
  checkpoint state.
- **Android API 29 requirement** — `PowerManager.addThermalStatusListener` is API 29+. Below
  that, fall back to battery temperature from `BatteryManager.EXTRA_TEMPERATURE` (in tenths
  of a degree Celsius); treat > 420 (42 °C) as `serious`.
- **Thermal state resets on app background** — when your app backgrounds, the SoC cools because
  you stop doing work. Do not assume `serious` at re-foreground; read the current state fresh.
- **`fair` state is often transient** — on newer A-series chips, `fair` lasts < 5 seconds
  during brief bursts. Debounce adaptation logic with a 3-second delay before degrading quality
  to avoid flicker.
- **Camera session contributes most to heat** — Vision Camera's frame processor pipeline with
  MLKit inference is the single largest thermal contributor in most media apps. Profile with
  Xcode Instruments → Thermal State to confirm.

---

## Verification

```bash
# iOS: simulate thermal state changes in Xcode
# Debug → Simulate → Thermal State → Fair / Serious / Critical
# (requires connected device or simulator running in Xcode 14+)

# Android: use adb to inject thermal status
adb shell cmd thermalservice override-status 3   # THERMAL_STATUS_SEVERE
adb shell cmd thermalservice reset
```

Verify that the `ThermalStateChange` event fires within 200 ms of the Xcode or ADB command,
that frame rate visibly drops in the video preview, and that the thermal warning banner appears
at `critical` without crashing.

---

## Related

- `mobile-battery-optimization.md` — general battery conservation patterns
- `mobile-performance-profiling.md` — Xcode Instruments and Android Profiler setup
- `react-native-vision-camera-v4.md` — frame processor throttling under thermal pressure
- `android-workmanager-background.md` — deferring background work during critical state

## Sources

- Apple ProcessInfo.ThermalState: https://developer.apple.com/documentation/foundation/processinfo/thermalstate
- Android PowerManager thermal: https://developer.android.com/reference/android/os/PowerManager#THERMAL_STATUS_NONE
- WWDC 2019 "Optimizing Your App for Today's Internet": https://developer.apple.com/videos/play/wwdc2019/712/
- Android thermal headroom: https://developer.android.com/games/optimize/thermal

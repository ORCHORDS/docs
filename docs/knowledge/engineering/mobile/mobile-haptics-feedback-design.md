# mobile-haptics-feedback-design

**Issue:** Haptic feedback is the most under-designed output channel in mobile apps. Done well, it confirms gestures, signals state transitions, and makes an app feel responsive before pixels update. Done badly, it fires on every tap, drains battery, and annoys users who cannot find a setting to disable it. The platform gap is large: iOS Core Haptics exposes a full event-composition engine (transient and continuous events with intensity and sharpness envelopes via CHHapticEngine), while Jetpack Compose's LocalHapticFeedback only exposes a handful of predefined constants, and only a subset of Android devices ship actuators good enough to reproduce custom effects. This article covers choosing APIs per platform, designing a haptic vocabulary, bridging haptics across a WebView shell (relevant to the Capacitor-based example project app, where Phase 4 explicitly includes haptics), and the pitfalls that only appear on real hardware.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Platform API Landscape

1. **Compose LocalHapticFeedback.** The standard Compose entry point via LocalHapticFeedback.performHapticFeedback covers LongPress and TextHandleMove constants only. It is fine for menu long-presses but cannot express success, warning, or ramped effects, so apps that need semantics beyond clicks must drop a level.

2. **VibratorManager and HapticAttributes.** For advanced effects on Android, go through VibratorManager (API 31+) with HapticAttributes that declare the usage context (touch, gesture start, physical button emulation). Using the right usage category lets the system scale effects for the device's actuator instead of you guessing amplitudes.

3. **Core Haptics CHHapticEngine.** iOS offers CHHapticEngine with transient (sharp taps) and continuous (sustained) events, each with intensity and sharpness parameters arranged in patterns. This enables designed vocabulary like a rising ramp for progress completion. Handle engine startup and stopped-engine callbacks; the engine is not always running.

4. **System-defined effects first.** Both platforms recommend system-defined primitives where possible (UIImpactFeedbackGenerator styles on iOS, HapticFeedbackType constants on Android). They are tuned by the OS vendor per device, so they feel consistent where custom envelopes feel broken on cheap actuators.

5. **The iOS-Android gap is real.** Software Mansion's comparison is blunt: Core Haptics gives full control over intensity, sharpness, timing, and composition; Android exposes limited primitives that vary by OEM. Design one vocabulary, then degrade gracefully per platform instead of forcing identical patterns.

## Designing a Haptic Vocabulary

1. **Reserve haptics for outcomes, not inputs.** Fire feedback when something completes, fails, or crosses a threshold — payment sent, biometric accepted, gesture committed. Firing on every button tap trains users to ignore haptics entirely and masks the events that matter.

2. **Three-tier intensity model.** Define light (selection changes, toggle), medium (action confirmed), and strong (destructive action armed, auth success) tiers in the design system. Every haptic in the app must map to exactly one tier, which makes review and off switches trivial.

3. **One semantic per pattern.** If a double-pulse means "copied to clipboard," it must never also mean "download finished." Users learn patterns subconsciously, and overloading them produces confusion worse than having no haptics.

4. **Respect user and system settings.** Check system haptic settings before firing, and expose an in-app toggle mapped to your tiers (users often want strong ones off but light ones on). Never route around a user-disabled setting.

## Cross-Platform and WebView Integration

1. **Abstract behind a HapticsPort.** Define a single interface (tap, success, warning, ramp) implemented per platform. Business logic calls semantics, not platform APIs, which keeps React Native, Compose, and Capacitor codebases calling the same names.

2. **Capacitor plugin bridge.** In a WebView shell, JavaScript cannot reach the haptic APIs; expose them through a small Capacitor plugin that maps semantic events to VibratorManager on Android and Core Haptics on iOS. Keep the bridge async and fire-and-forget so UI never waits on haptics.

3. **Feature-detect, do not version-detect.** Capability checks (VibratorManager availability, CHHapticEngine support, actuator amplitude control) are more reliable than OS version gates, because OEM hardware variance on Android is wider than API-level variance.

4. **Throttle repeat events.** Continuous gestures (sliders, scrubbing) can request hundreds of haptic ticks per second. Throttle to 10-15 events per second maximum, and coalesce rapid repeats into amplitude ramps instead of discrete pulses.

## Testing and Common Pitfalls

1. **Test on real hardware only.** Emulators and simulators cannot reproduce haptics; a pattern authored in docs will feel completely different in the hand. Test on at least one flagship with a good actuator and one budget device without.

2. **Device variance is enormous.** An intensity 0.4 continuous event reads as a strong buzz on some Android phones and is imperceptible on others. Prefer relative system-scaled effects; when using raw amplitudes, test across OEMs (Samsung, Pixel, Xiaomi at minimum).

3. **Silent, battery-saver, and game modes.** Several OEM layers suppress or alter haptics under battery saver or focus modes. Verify critical haptics (auth result) have a visual fallback, since users may never feel them in these states.

4. **Battery cost of enthusiasm.** Frequent vibrator wake-ups show up in battery diagnostics and Play vitals. Cap total haptic events per session during rollout and watch the metrics; users punish battery-hungry apps faster than they reward fancy buzzes.

5. **Accessibility coherence.** Pair every haptic with visual or audio confirmation. Haptics are an enhancement channel, never the sole channel, for conveying state — deaf and haptic-insensitive users must lose nothing.

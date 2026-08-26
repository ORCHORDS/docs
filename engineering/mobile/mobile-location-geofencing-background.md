# mobile-location-geofencing-background

**Issue:** Reacting to location while the app is backgrounded — arrival triggers, delivery handoffs, home-automation geofences, branch proximity — is the most policy-constrained capability on mobile. Google Play restricts ACCESS_BACKGROUND_LOCATION to apps where location is core functionality with clear user benefit, requires a Play Console declaration with a demo video, and rejects apps that request it casually; Apple gates Always authorization behind a two-step prompt and audits usage. Meanwhile the APIs themselves surprise engineers: geofence events are deferred under Doze, fences are wiped at reboot, radius accuracy is limited to roughly 100 meters regardless of what you register, and battery/accuracy tradeoffs are set per request. This article covers permission strategy, API selection, reliability engineering, and the privacy posture needed to pass review on both stores.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Permission Model and Store Review

1. **While-in-use first.** Register geofences under ACCESS_FINE_LOCATION with foreground-only ("While in use") permission wherever possible. Geofencing transitions can often still be delivered with the app in use, which avoids the entire background-location review track for many products.

2. **The Play declaration and video.** If background delivery is genuinely core, you must complete the Play Console declaration, including a short video demonstrating the in-app disclosure flow and the background behavior. Rejections here are common and manual; script the video to show disclosure, prompt, and one real background trigger.

3. **Prominent disclosure before runtime prompt.** Google requires a visible in-app disclosure (what data, why, how used) shown before the OS permission dialog for background location. Burying the rationale in a wall of text fails review; a dedicated screen with an accept action is the pattern reviewers expect.

4. **iOS Always is a two-step dance.** iOS initially grants When In Use even when Always is requested; the system later re-prompts. Design the flow to request When In Use first, prove value, then upgrade to Always — requesting Always cold gets users to deny everything.

## Choosing the Right API

1. **Geofencing API for fences.** Use the platform geofencing APIs (Android GeofencingClient, iOS CLCircularRegion monitoring) rather than continuous tracking plus your own geometry. The OS wakes your process on transitions and handles the radio duty-cycling, which no app-level polling loop can match.

2. **FusedLocationProvider for tracks.** If the product needs routes or distance (delivery tracking, fitness), use FusedLocationProvider on Android with explicit priority levels (PRIORITY_BALANCED_POWER_ACCURACY versus HIGH_ACCURACY) rather than the raw LocationManager, and only inside a foreground service with the location type.

3. **Significant-change monitoring on iOS.** CLMonitor (iOS 17+) and significant-location-change APIs wake the app on cell-tower-scale movement at minimal battery cost. Use them as the coarse trigger, then confirm with region monitoring or a short foreground burst.

4. **Never poll on a timer.** Timer-driven location polls defeat platform batching, surface in battery vitals, and are the top cause of "why was my app killed" reports. All location work should be event-driven from the OS.

## Reliability Engineering

1. **Radius floor of 100 meters.** Geofence radius accuracy bottoms out around 100 m regardless of the registered value; smaller fences produce missed or flapping transitions. For tighter triggers (building entry), combine a coarse geofence with Beacons or NFC rather than fighting physics.

2. **Dwell versus enter triggers.** Use GEOFENCE_TRANSITION_ENTER for arrival notifications but DWELL (with a loitering delay) for actions with side effects. DWELL filters out GPS jitter and drive-bys, which is the difference between "Welcome home!" and spam.

3. **Re-register after reboot.** Android clears registered geofences on reboot; a BOOT_COMPLETED receiver (or WorkManager on-boot expedited work) must re-register them. Forgetting this is the single most common production geofencing bug — fences silently stop working until the user opens the app.

4. **The 100-geofence limit.** Android caps registered geofences at roughly 100 per app. Prioritize fences around the user's current location and rotate registrations as they move, rather than registering the entire estate up front.

5. **Doze and App Standby defer events.** Transition broadcasts are batched and delayed under Doze. If timing matters, escalate to a foreground service with the location type (Android 14+ requires declaring it in the manifest and at runtime), accepting the notification-bar cost.

## Battery and Privacy Posture

1. **Defer to platform power modes.** Balance accuracy priorities downward whenever the interaction allows; a coffee-shop arrival alert does not need high accuracy. Radio time is the dominant battery cost, not CPU.

2. **Data minimization by design.** Process geofence events on-device and upload transitions, not tracks, unless the product demands traces. Reviewers and regulators both respond better to "we store events, not location history."

3. **Privacy labels and consent records.** iOS privacy nutrition labels and Play data-safety forms must match observed behavior. Keep a consent record (when prompted, what granted) — Google Play issue-finding has automated mismatch detection.

4. **Respect the indicator era.** Both OSes now show persistent indicators for location access, and iOS shows the recent-access chip in Control Center. Any background use the user cannot mentally map to a feature reads as surveillance; annotate triggers in-app ("We noticed you arrived at...").

## Testing Strategy

1. **Mock locations and GPX replay.** Use ADB emu geo fix, mock location providers, and Xcode GPX replays to drive transitions deterministically in CI-adjariant tests; field-testing geofences by walking around the block does not scale and cannot test dwell windows.

2. **Doze and reboot drills.** Explicitly test: force-stop, reboot, Doze on (adb shell dumpsys deviceidle force-idle), and App Standby buckets. These four states account for nearly all "geofence stopped working" support tickets.

3. **Cross-device variance.** OEM process killers (Samsung, Xiaomi, Oppo) aggressively terminate background receivers. Test on the actual target fleet (the S22 test device for example project work), and document per-OEM battery-optimization exemption instructions in support content.

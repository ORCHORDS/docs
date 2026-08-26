# mobile-bluetooth-le-connections

**Issue:** Bluetooth Low Energy (BLE) is the transport behind wearables, fitness trackers, smart locks, heart-rate monitors, and IoT accessories, but it is one of the most fragmented APIs in mobile engineering. Android overhauled its permission model in Android 12, splitting scan/connect/advertise into separate runtime permissions, while iOS restricts background scanning to specific service UUIDs and aggressively suspends apps. Teams that treat BLE like a simple socket API ship apps that fail to connect after screen-off, burn battery with continuous scans, get rejected for missing permission declarations, or silently break on Android 11 devices still using the legacy permission stack. A BLE layer must be designed around per-platform permission matrices, background execution limits, and the inherent unreliability of radio connections.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Android permission model

1. **Runtime permissions since Android 12.** BLUETOOTH_SCAN, BLUETOOTH_CONNECT, and BLUETOOTH_ADVERTISE are dangerous runtime permissions (API 31+). Scanning without them throws SecurityException, so the app must request them contextually and handle denial gracefully rather than assuming grant at startup.
2. **The neverForLocation flag.** If the app does not derive physical location from BLE beacons, declare BLUETOOTH_SCAN with android:usesPermissionFlags="neverForLocation". Without it, scan results are filtered by whether the user granted location, which causes "no devices found" bugs that look like hardware failures.
3. **Legacy stack for Android 11 and below.** Devices on API 30 and older still need BLUETOOTH and BLUETOOTH_ADMIN (declared with android:maxSdkVersion="30") plus ACCESS_FINE_LOCATION for scanning. The manifest must carry both permission generations simultaneously, and the request flow must branch on Build.VERSION.
4. **Request at the moment of need.** Asking for scan/connect permissions before the user has touched a "pair device" flow trains users to deny. Show a pre-permission explainer, then request when the user initiates discovery.

## iOS background constraints

1. **The bluetooth-central background mode.** Background BLE only works if the bluetooth-central UIBackgroundMode is declared. Even then, scanning must target specific service UUIDs — a nil-service wildcard scan returns nothing in the background.
2. **State restoration.** Create CBCentralManager with the CBCentralManagerOptionRestoreIdentifierKey option and implement centralManager(_:willRestoreState:) so iOS can relaunch a terminated app when a peripheral connects or disconnects. On relaunch the app must re-instantiate its managers before using restored peripherals.
3. **Force-quit disables restoration.** If the user swipes the app away, iOS will not relaunch it for Bluetooth events. Design the UX so reconnection happens on next foreground rather than promising always-on background connectivity.
4. **Background scan timing is randomized.** iOS stretches and randomizes scan intervals in the background to save power; connection latency to a peripheral can take many seconds. Never use background scanning for time-critical flows like access-control unlock.

## Connection lifecycle design

1. **Connect with autoConnect on Android sparingly.** GATT connect with autoConnect=true lets the stack reconnect when the device appears, but it can take minutes and holds a wakelock. For user-initiated sessions use direct connect with a timeout, then fall back to autoConnect only if the product expects background reconnection.
2. **Serialize GATT operations.** Only one outstanding operation per connection is reliable: wait for onCharacteristicWrite/onCharacteristicRead callbacks before issuing the next. Queue requests in a state machine instead of firing them concurrently, which is the top cause of Status 133 (GATT_ERROR) on Android.
3. **Handle bonding variations.** Some peripherals require LE Secure Connections pairing before readable characteristics; others use Just Works. Listen to bond-state changes and surface a human-readable pairing step instead of a raw stack error.
4. **Refresh device cache deliberately.** Android caches GATT service discovery results; after firmware updates that change the GATT table, call the hidden refresh path (or disconnect/reconnect) strategy — stale cached services are a classic "works after reinstall only" bug.

## Reliability and testing

1. **Assume every operation can fail.** Wrap connect, discover, read, write, and subscribe with timeouts and retry with exponential backoff. BLE radios interfere with Wi-Fi (2.4 GHz) and other peripherals; transient failures are normal, not exceptional.
2. **Test on mid-range and old devices.** Bluetooth stack behavior differs wildly between Samsung, Pixel, and budget chipsets. A matrix covering at least Android 11, 13, and 15 plus two iOS versions catches the worst permission and timing regressions.
3. **Instrument connection metrics.** Log scan-to-connect time, connect success rate, and disconnect reasons (GATT error codes, iOS CBError domain codes) to analytics. Field BLE bugs are nearly impossible to reproduce without disconnect reason telemetry.
4. **Battery guardrails.** Stop scans when the screen leaves the foreground unless background scanning is a product requirement, batch characteristic reads, and avoid polling — prefer subscriptions (notifications/indications) which let the peripheral push data and let both radios sleep.

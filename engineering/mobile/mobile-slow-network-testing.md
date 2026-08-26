# mobile-slow-network-testing

**Issue:** Most mobile bugs reported as "the app hangs," "white screen forever," "my message sent twice," or "login broken on the train" only reproduce on degraded networks — 2G-class bandwidth, hundreds of milliseconds of latency, packet loss, or mid-request drops. Office Wi-Fi and flagship phones on 5G hide all of them. This article is the QA-side counterpart to `mobile-network-resilience.md` (which covers the code patterns): how to reliably reproduce slow and flaky networks on Android emulators, iOS devices/simulators, hybrid WebView apps, and CI, plus the edge cases (captive portals, DNS failure, IPv6-only, metered networks) almost nobody tests until users hit them.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Shaping tools per platform

1. **Android emulator network flags.** Launch with `emulator -avd <name> -netspeed edge -netdelay 400` (or `gsm`, `umts`, `hsdpa` presets; numeric like `-netspeed 14.4 80` also works). Change it live per test run via Extended Controls > Cellular in the running emulator (Android Studio) — no restart needed, which matters for mid-session degradation tests.
2. **Real Android devices via adb.** Emulator flags don't apply to physical hardware. On a rooted/engineering device, `tc qdisc`/`netem` via `adb shell` works; otherwise pair the device to a throttled laptop hotspot (below) or use cloud farms (BrowserStack App Live, AWS Device Farm, Firebase Test Lab) which expose per-session network profiles — cloud farms are also the only realistic path for CI-integrated network-condition runs.
3. **iOS/macOS Network Link Conditioner.** Install from Additional Tools for Xcode; on a real iOS device enable Settings > Developer > Network Link Conditioner (after enabling the device as dev hardware). Built-in profiles include "Edge" (~2G-class), "3G," "High Latency DNS," "Very Bad Network" (drops packets), and custom profiles (e.g. 50 kbps / 800 ms RTT / 2% loss) approximate real emerging-market 2G. It shapes the whole device/system — perfect for end-to-end realism, terrible for parallel tests.
4. **Proxy-level throttling for hybrid apps.** Charles Proxy (Throttle presets, per-host rules, and macOS system-level shaping), Proxyman, or `toxiproxy` on localhost give per-connection control: slow only your API host, leave assets fast. This is the right tool for Capacitor/WebView apps (the example project mobile shell loads example.com) where Chrome DevTools throttling only covers the WebView's requests, not native plugin traffic.
5. **toxiproxy / tc for deterministic chaos in CI.** Run `toxiproxy` as a sidecar (or `tc netem` on the CI runner's veth pair) and inject `timeout`, `slow_read`, `bandwidth`, and `down` toxins programmatically between the app-under-test and a local mock API. This is the only approach that can make e2e suites (Detox, Appium, Maestro) assert on degraded-network behavior repeatably instead of hoping the throttler engages.

## The degradation scenarios worth scripting

1. **Slow-but-steady 2G.** ~50 kbps down, high RTT, no loss. Asserts: skeletons/spinners render, requests time out sanely, images load progressively or not at all, and the UI thread never blocks on responses (watch via Profiler / Instruments while shaping is active).
2. **Mid-request kill.** Toggle airplane mode (or `adb shell svc data disable` / `svc wifi disable`) exactly while a POST is in flight; then restore. Verifies retry/idempotency keys prevent double-submits — the "payment taken twice" class of bug. On iOS, toggling the NLC profile to 100% loss is a cleaner trigger than the control-center airplane toggle.
3. **Flapping connectivity.** Alternate 10 seconds up / 5 seconds down in a loop while the user scrolls. Exposes reconnect storms, WebSocket clients that don't back off, and NetInfo-driven listeners that re-fire dozens of times (see `react-native-netinfo.md` gotchas).
4. **High-latency DNS / DNS failure.** NLC's "High Latency DNS" profile or a proxy rule blackholing port 53 surfaces apps that block the main thread on first-resolver use, and apps with no timeout on hostname resolution. Assert a bounded error state, not an infinite splash.
5. **Captive portals.** Join a hotspot that answers DNS but returns a portal redirect (any hotel/airport Wi-Fi, or simulate with a proxy returning 302 + portal HTML for all requests). The app must not treat the portal as your API: JSON-parse failures on portal HTML cause fake "server error" toasts and, worse, token-refresh flows that store the portal page.

## Edge cases beyond bandwidth

1. **IPv6-only networks (NAT64/DNS64).** Apple requires IPv6 compatibility testing and rejects apps that break on IPv6-only Wi-Fi (Test it: Mac Internet Sharing "Create NAT64 Network" checkbox, then connect the device). Hardcoded IPv4 literals, socket code that skips `getaddrinfo`, and SDKs with IPv4-only CDN pins are the usual offenders.
2. **Metered/slow-roaming detection.** Android `ConnectivityManager.isActiveNetworkMetered()` and cap-state APIs decide whether big prefetches are acceptable; test with the emulator's cellular data + "data saver on" toggles. iOS has no public metered flag — use `NWPathMonitor` constraints and reachability as a proxy, and design defaults conservatively (see `pwa-offline-caching-strategies.md` for the web-side equivalent).
3. **Request succeeds, response never arrives.** Use a proxy "cut connection after request received" rule (Charles break-point + drop, toxipropy `timeout` post-request). Apps must retry idempotent GETs but never blind-retry the payment POST — pair this test with the dedup-token checks from `mobile-network-resilience.md`.
4. **Partial media/progressive downloads on lossy links.** 2% packet loss with large payloads shows whether image pipelines (see `mobile-image-caching-patterns.md`) stall forever, and whether upload logic resumes (`Range`/session resumption) or restarts from byte zero every failure — the difference between minutes and never on 2G.
5. **Background/foreground transitions under load.** Throttle on, background the app mid-download, wait 30s, return. Combined with process-death testing (`mobile-app-lifecycle-process-death.md`) this is where "restore shows done but the file is truncated" bugs live. Verify with the logcat + screenshot-per-step protocol.

## Making it stick (process, not heroics)

1. **Fix a named throttle profile in the repo.** Commit the exact numbers ("2G-poor": 50 kbps / 800 ms RTT / 2% loss / 300 ms DNS) so "tested on 2G" means one thing across QA, devs, and CI — not whatever preset someone clicked. Include an NLC `.terminal`-importable custom profile or the emulator flag string in the test plan.
2. **Run one CI lane degraded, always.** A nightly e2e lane through toxiproxy with the 2G-poor profile plus a mid-test `down` toxin catches regressions the fast lanes can't. Fail the lane on unhandled network errors in logs (the same grep set as the example project logcat protocol: `timeout|refused|reset|ERR_`).
3. **Set time-based budgets and assert them.** Define SLAs at P95 (e.g. first meaningful content < 10 s on 2G-poor, error state < 5 s on total loss) and assert in the e2e suite with wall-clock timers rather than eyeballing spinners — perceived performance on slow networks is the actual product requirement in emerging markets.
4. **Test on the real device class, not just the throttled flagship.** Shaping a Samsung S22 to 50 kbps still hides slow TLS handshakes on weak CPUs and low-RAM process kills; pair throttling with midrange/Android-Go profiles for representative results.
5. **Log network-quality context into crash/analytics events.** Attach effective connection type, RTT estimate, and offline-transition counters to error reports so production "hang" reports can be triaged as network-class vs code-class — Sentry breadcrumbs or custom middleware both work (see `mobile-crash-reporting.md`).

## Related

- `mobile-network-resilience.md` — the code patterns this article verifies
- `react-native-netinfo.md` — connectivity listeners under flapping
- `mobile-e2e-testing.md` / `mobile-testing-detox.md` — wiring these scenarios into automation
- `mobile-app-lifecycle-process-death.md` — backgrounding mid-transfer

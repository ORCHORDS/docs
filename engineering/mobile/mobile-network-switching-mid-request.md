# mobile-network-switching-mid-request

**Issue:** Phones change networks constantly — WiFi to cellular when leaving the house, cellular to office WiFi mid-download, WiFi to airplane-mode for a second when the OS flaps. What happens to an in-flight HTTP request during the switch is where mobile apps break: requests die with opaque errors, some client stacks silently retry and accidentally double-submit a payment, uploads restart from byte zero, and WebSockets hang in a half-open state until a TCP timeout minutes later. This is distinct from general "network resilience" (offline caching, retry policies): it is specifically about connection *migration* — surviving (or safely failing and retrying) the handover itself without duplicating side effects.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What actually happens when the network switches mid-request

1. **The TCP connection's source IP disappears, and the socket dies.** Switching WiFi→cellular changes the local address; existing TCP connections are not portable, so the OS tears them down. In-flight requests surface as `SocketException`, `ECONNRESET`, `kCFErrorDomainNetwork`-style failures — not as clean HTTP error codes, so HTTP-layer error handling (4xx/5xx switches) never runs.
2. **The OS gives no guaranteed "switch happened" callback to your request layer.** Android's `ConnectivityManager.NetworkCallback` fires `onAvailable`/`onLost`, iOS's `NWPathMonitor` updates paths, but your HTTP client sees only the resulting IO error. Subscribing to connectivity events tells you *why* a failure happened (safe to retry immediately) — it does not prevent the failure.
3. **DHCP flaps and captive portals produce phantom switches.** Brief WiFi drops, hotel/airport captive portals, and VPN connect/disconnect all hand the app a "new network" that may be worse than the last. Retrying eagerly into a captive portal burns battery and returns HTML login pages that JSON parsers crash on — validate the first response after any handover.
4. **Half-open connections are the silent killer.** If the switch drops only the *return* path (common with NAT timeout + WiFi handover), the client never learns the connection is dead: the request "hangs" until TCP keepalive or your read timeout fires. Always set explicit per-request timeouts (connect + read); infinite-default clients turn a 200ms handover into a 60s UI freeze.
5. **Different radios fail differently.** WiFi→cellular handover usually completes in a few seconds (request fails fast, retry succeeds); cellular→WiFi mid-request often stalls because the old interface lingers. Test both directions — teams regularly test only "left the house" and not "walked into the office."

## iOS: Multipath TCP, waitsForConnectivity, and NWPathMonitor

1. **Multipath TCP (handover mode) is the purpose-built tool.** With the Multipath Entitlement and `URLSessionConfiguration.multipathServiceType = .handover`, URLSession starts the request on WiFi and hands it to cellular transparently if WiFi drops — the request never surfaces an error (Apple: "Improving network reliability using Multipath TCP"). `.interactive` and `.aggregate` exist for lower-latency and bandwidth-aggregation use; `.handover` is the default recommendation. Caveats: your *server* must support MPTCP (or traffic falls back transparently), and cellular use counts against user data plans.
2. **`waitsForConnectivity` turns hard failures into delayed starts.** Instead of failing a request instantly when no usable path exists, the session waits (calling the task delegate's `urlSession(_:taskIsWaitingForConnectivity:)`) and starts when a path appears — ideal for background fetches that should ride out a tunnel or elevator. It does nothing for requests already in flight; pair it with MPTCP for full coverage.
3. **Use `NWPathMonitor`, not `SCNetworkReachability` or a fake ping.** `NWPathMonitor` is the modern path-change API (unsatisfied / satisfied / expensive, per-interface details) and its `isExpensive` flag is how you detect cellular/hotspot for metered gating. Don't gate requests on a connectivity check before sending ("check then act" races with the switch) — send the request, handle the error, use the monitor only to inform retry policy and UI.
4. **Background sessions survive switches for downloads/uploads.** `URLSession` background sessions continue transfers across app suspension and network changes (the system retries); for large uploads/downloads they are the robust answer, with `URLSessionDownloadTask` resume data (or server-side range requests) for continuation. Foreground data tasks get none of this for free.
5. **Watch for iOS's WiFi Assist asymmetry.** iOS may route traffic over cellular while WiFi looks fine (WiFi Assist), so "connected to WiFi" UX assumptions can be wrong; use `NWPath` details, not the WiFi icon's implied contract.

## Android: OkHttp behavior, network callbacks, and constraints

1. **OkHttp silently retries — including some non-idempotent POSTs.** With `retryOnConnectionFailure` (default true), OkHttp re-routes a request to a fresh route/connection when the current one fails mid-request, including after a WiFi→cellular switch. As the Inloopx write-up ("OkHttp is quietly retrying requests. Is your API ready?") documents, a request that already transmitted its body can be re-sent, double-executing a non-idempotent operation server-side. This is a payment-duplication class of bug.
2. **Decide per request: silent retry vs explicit retry.** For idempotent GETs, keep `retryOnConnectionFailure(true)`. For non-idempotent POSTs (pay, send, book), disable retry on that client (`Builder().retryOnConnectionFailure(false)`) and implement application-level retry with idempotency keys — you, not the socket layer, choose when a second attempt is safe.
3. **Register a `ConnectivityManager.NetworkCallback` to classify errors and drive UI.** `onCapabilitiesChanged` gives you `NET_CAPABILITY_VALIDATED` and `NET_CAPABILITY_NOT_METERED` — validated-but-not-metered is how you distinguish "real internet" from captive portals and meter WiFi from free WiFi. Use `onLost`/`onAvailable` to flip a "reconnecting..." banner and to *pause* upload queues instead of burning retries into a dead interface (per `mobile-network-resilience.md` and `react-native-netinfo.md` patterns).
4. **Request a network you can keep with `NetworkRequest`.** `ConnectivityManager.requestNetwork` with `TRANSPORT_CELLULAR`/`TRANSPORT_WIFI` lets you pin a request to a specific network (via OkHttp's `socketFactory` from `net.socketFactory`), useful for dual-transport apps (signaling over cellular while bulk transfers use WiFi). Binding to one network also makes handover behavior deterministic rather than OS-whimsical.
5. **Honor the main-line docs on retries: exponential backoff + jitter.** A handover storm (subway, elevator) plus naive immediate retries creates a thundering herd on the new interface. Back off with jitter, cap attempts, and let the upload queue persist across process death (WorkManager + local queue per `android-workmanager-background.md`).

## Idempotency keys and safe retries across both platforms

1. **Generate a client-side idempotency key per logical operation.** UUID (or deterministic hash of operation + parameters) sent as `Idempotency-Key` header; the server stores key→response for a TTL window and replays the stored response on duplicates. This is the only scheme that makes "retry after handover" safe for payments, sends, and creates — both you and the stack under you may retry, so the server must dedup.
2. **Persist the key before the first attempt, not in memory.** If the process dies mid-request (process death + network switch in sequence is common — see `mobile-app-lifecycle-process-death.md`), the relaunched app must reuse the same key to reconcile: query the operation's status by key on startup instead of blind-resubmitting ("did my payment go through?" is answered by the server, not by optimism).
3. **Use range requests and resumable uploads for bulk transfers.** Handovers during multi-MB uploads are guaranteed; restart-from-zero wastes user data. Chunked/resumable protocols (tus-style, S3 multipart, or plain HTTP Range for downloads) bound the loss to one chunk per switch.
4. **Make WebSocket/SSE reconnects first-class.** Long-lived sockets die on every handover: reconnect with backoff, re-authenticate, and resubscribe with a `Last-Event-ID`/cursor so missed server events backfill rather than vanish. A chat app that loses the tail of a conversation during every subway ride has a handover bug, not a "flaky network" problem.
5. **Tag analytics with the failure transport.** Log error + current network type + whether a switch happened in the last N seconds (from the connectivity monitor). Handover-related failures cluster under `SocketException`/`ETIMEDOUT`; making them visible as a category is step one to fixing them systematically.

## Testing handover behavior (not just offline)

1. **Run the example project wifi-off/wifi-on test steps against in-flight operations.** The AGENTS.md protocol (`09-wifi-off`, `10-wifi-on`) exists for this: start a payment/upload/download, toggle WiFi off mid-flight, screenshot and check logs, toggle back on, and verify the outcome — no duplicate charges, upload resumes, UI shows the right state. Airplane-mode-then-on and cellular-only (WiFi off entirely) are different scenarios; run both.
2. **Use the emulator's network simulation plus a physical device.** Emulator extended controls can throttle and drop, but only real radio handovers reproduce timing: on a physical device, walk WiFi→cellular (leave WiFi range), cellular→WiFi (walk back), and WiFi-flap (toggle router). Cellular→WiFi stalls only reproduce on hardware.
3. **Test with captive portals and VPNs explicitly.** Join a captive-portal network mid-session (any coffee-shop WiFi works) and connect/disconnect a VPN during a request — these produce the "JSON parser got HTML" and "request went out the wrong tunnel" bugs that plain on/off testing never finds.
4. **Assert the no-duplicate invariant in E2E.** For every non-idempotent endpoint, the E2E suite should toggle the network mid-request and then assert server state (exactly one order created). This is the test that catches OkHttp's silent retry duplicating a POST — and it fails loudly, in CI, instead of in a support ticket.

## Related

- `mobile-network-resilience.md`
- `react-native-netinfo.md`
- `mobile-slow-network-testing.md`
- `android-retrofit-patterns.md`
- `ios-urlsession-patterns.md`

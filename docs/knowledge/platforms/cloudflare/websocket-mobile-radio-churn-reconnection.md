# WebSocket Connection Churn on Mobile Networks vs Desktop

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Mobile users of example project (example.com) report missed chat messages and
presence indicators that flap online/offline, while desktop QA cannot
reproduce either. Server logs show mobile clients reconnecting every
few minutes; desktop sockets stay open for hours. After a subway ride
or a WiFi-to-cellular handoff, a burst of reconnects hits the same
Durable Object at once. Some mobile connections die silently: the
client believes it is connected but discovers the dead socket only
when the user sends a message that never arrives.

## Context

A WebSocket is a plain TCP connection, and mobile networks are hostile
to long-lived idle TCP. Three independent mechanisms kill mobile
sockets that desktop never sees: the cellular radio state machine (RRC
transitions drop the radio to idle within seconds of inactivity, and
OSes suspend backgrounded apps — iOS gives background apps seconds,
Safari freezes hidden tabs, Android Doze batches network access);
carrier-grade NAT gateways that silently expire idle mappings (often
30-120s on cellular, with some carriers requiring keepalives under
270s even for TCP); and network transitions (WiFi to cellular) that
change the client IP, which invalidates the TCP 4-tuple — there is no
TCP migration, only reconnect. Cloudflare's proxy adds its own ~100s
idle timeout for WebSockets. Realtime features must therefore be
designed around churn: mobile median connection lifetime is minutes,
not hours, and the server-side session must outlive any one socket.

## Why mobile sockets die: radio, OS, and browser lifecycle

```
Layer                Desktop behavior        Mobile behavior
──────────────────────────────────────────────────────────────────
Radio / link         Ethernet/WiFi always    RRC state machine:
                     on, no idle teardown    radio drops CONNECTED →
                                             idle after seconds of
                                             no traffic; waking it
                                             costs latency + battery
OS app lifecycle     Apps run for days;      iOS suspends background
                     sockets survive         apps in seconds; Android
                     minimized windows       Doze defers network for
                                             backgrounded apps
Browser tabs         Hidden tabs keep        Safari freezes hidden
                     sockets (throttled      tabs and kills sockets
                     timers only)            on screen lock — often
                                             with NO close event;
                                             timers stop entirely
Result               Socket lifetime:        Socket lifetime:
                     hours to days           seconds to minutes
```

Key consequence: on mobile you cannot rely on a `close` event ever
firing. iOS Safari suspends the page, the socket dies upstream, and
on resume the client holds a zombie socket in `readyState OPEN` that
only an application-level heartbeat timeout can detect.

## Idle timeouts along the path — heartbeat must beat the minimum

```
Hop                       Typical idle timeout
──────────────────────────────────────────────────────────────────
Cellular carrier NAT      30-120s common; measured as low as ~28s
(CGNAT)                   on one US LTE carrier; one EU carrier
                          needed TCP keepalive <= 270s
Home/WiFi router NAT      60-300s
Cloudflare proxy (WS)     ~100s (Enterprise can raise it)
Nginx / AWS ALB origin    60s default
Google Cloud LB           30s default

Rule: heartbeat interval ≈ 75% of the SHORTEST timeout in the
path. Behind Cloudflare + cellular CGNAT, use 20-30s pings.
```

The drop is silent: NAT gateways expire the mapping without sending
RST/FIN, so both ends keep a socket that routes nowhere. Heartbeats
refresh NAT/proxy idle timers, and a missed pong is the only reliable
zombie detector. With the Hibernation API, use auto-response so pings
do not wake the DO:

```typescript
// In the Durable Object constructor — replies to pings while
// hibernated, at zero duration cost, and refreshes CF's idle timer
this.ctx.setWebSocketAutoResponse(
  new WebSocketRequestResponsePair('ping', 'pong')
);
```

Client side: send `'ping'` every 25s, and if 2-3 pongs are missed,
tear down and reconnect — do not wait for a close event.

## Network transitions: IP changes mean reconnect, not resume

TCP connections are identified by (src IP, src port, dst IP, dst
port). A WiFi-to-cellular handoff gives the phone a new IP, so every
open TCP socket is instantly invalid — TCP has no migration. QUIC
fixes this with connection IDs and PATH_CHALLENGE path migration, but
WebSockets ride TCP (RFC 6455) — so plan for reconnects instead.

A cell handoff or tower outage disconnects thousands of clients at
once; naive reconnect loops then stampede the same DO. Protect with
jittered exponential backoff plus a resume token:

```typescript
let attempt = 0;
function reconnect() {
  // full jitter: random(0, min(30s, 1s * 2^attempt))
  const cap = Math.min(30_000, 1000 * 2 ** attempt);
  const delay = Math.random() * cap;
  setTimeout(() => {
    attempt++;
    const url = `wss://ws.example.com/room/${roomId}` +
      `?resume=${sessionToken}&last_seq=${lastSeq}`;
    open(url); // on successful hello: attempt = 0
  }, delay);
}
```

Reconnect immediately (no backoff) on `online`/foreground events —
those are genuine "network is back" signals, not failures.

## Designing Durable Objects for churn: session outlives socket

Treat the socket as disposable and the DO as the session. The
Hibernation API makes churn cheap (no duration billing between
messages); `serializeAttachment` plus a per-room sequence number
gives gap-free resume:

```typescript
async webSocketMessage(ws: WebSocket, raw: string | ArrayBuffer) {
  const msg = JSON.parse(raw as string);
  if (msg.type === 'post') {
    const seq = ((await this.ctx.storage.get<number>('seq')) ?? 0) + 1;
    await this.ctx.storage.put('seq', seq);
    await this.ctx.storage.put(`msg:${seq}`, msg.body); // replay buf
    for (const peer of this.ctx.getWebSockets()) {
      peer.send(JSON.stringify({ seq, body: msg.body }));
    }
  }
}

async fetch(request: Request): Promise<Response> {
  // ...upgrade handling elided (see workers-websocket-upgrade.md)
  const lastSeq = Number(url.searchParams.get('last_seq') ?? 0);
  this.ctx.acceptWebSocket(server);
  server.serializeAttachment({ userId, lastSeq });
  // Replay everything the client missed while disconnected
  const cur = (await this.ctx.storage.get<number>('seq')) ?? 0;
  for (let s = lastSeq + 1; s <= cur; s++) {
    const body = await this.ctx.storage.get(`msg:${s}`);
    if (body) server.send(JSON.stringify({ seq: s, body }));
  }
  return new Response(null, { status: 101, webSocket: client });
}
```

Presence: never mark a user offline on raw socket close. Debounce
with a DO alarm (e.g. 60s grace) so quick reconnects cause no flap.
Client lifecycle on mobile browsers — pause on hide, resume on show:

```javascript
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') {
    stopHeartbeat();            // timers will be frozen anyway
  } else {
    sendPingNow();              // probe for zombie socket
    if (socketDead()) reconnect(); // immediate, attempt = 0
  }
});
// pagehide fires more reliably than unload on iOS Safari
window.addEventListener('pagehide', () => ws.close(1000, 'pagehide'));
```

## Metrics: segment everything by platform

```
Metric                     Desktop typical    Mobile typical
──────────────────────────────────────────────────────────────────
Median socket lifetime     hours              2-10 minutes
Reconnects per user-hour   < 1                5-30
Zombie detections          rare               common after resume
Replay gap size (msgs)     ~0                 1-50 after handoff

Alert on the RATIO shifting, not absolute counts: rising mobile
reconnect rate with stable desktop = network-path change (e.g.
heartbeat now slower than a carrier's NAT timeout), not a bug in
the app. Aggregated metrics hide this — desktop volume drowns
the mobile signal, which is why desktop QA "cannot reproduce".
```

## Anti-patterns

- **Tuning heartbeats above 100s** — Cloudflare's proxy idle timeout
  closes the socket first; cellular CGNAT often closes it by 30-60s.
  A 5-minute ping interval guarantees silent drops on mobile.
- **Trusting the close event** — iOS Safari and suspended apps kill
  sockets without delivering `close`. Detect death via missed pongs
  and probe on `visibilitychange`, never by waiting.
- **Immediate retry loops on disconnect** — a cell handoff
  disconnects a whole tower's worth of users; synchronized retries
  thundering-herd the same DO. Always jitter the backoff.
- **Presence tied 1:1 to socket state** — every mobile reconnect
  becomes an online/offline flap. Debounce disconnects with a grace
  window (DO alarm) before broadcasting offline.
- **Desktop-only QA for realtime features** — desktop sockets live
  orders of magnitude longer; churn bugs (replay, resume, presence)
  only surface with real mobile radio behavior or forced testing.

## Gotchas

- **Heartbeats keep the phone's radio up** — every ping forces an RRC
  idle→connected transition, costing battery. Do not ping faster than
  needed, and stop pinging while hidden (timers freeze anyway).
- **Hibernation auto-response is the cheap keepalive** —
  `setWebSocketAutoResponse` answers pings without waking the DO.
  Handling pings in `webSocketMessage` bills wake-up duration for
  every ping from every client.
- **`serializeAttachment` is capped at 2048 bytes** — store only the
  resume cursor (userId, lastSeq) there; keep the replay buffer in
  DO storage.
- **In-flight messages during reconnect are lost without seqs** —
  a message broadcast between the NAT drop and the client noticing is
  gone unless the client re-requests by last-seen sequence number.
- **Foreground resume needs an immediate probe** — the socket may be
  a zombie in `readyState OPEN`; ping with a 2-5s timeout before
  trusting it.

## Verification

- Client heartbeat interval is 20-30s, under both Cloudflare's ~100s
  proxy timeout and typical cellular CGNAT timeouts.
- DO uses `setWebSocketAutoResponse` so pings do not wake it.
- Reconnect uses full-jitter exponential backoff, reset on success
  and bypassed on foreground/`online` events.
- Messages carry sequence numbers; reconnect replays from `last_seq`
  with no user-visible gap.
- Presence offline is debounced via DO alarm, not raw socket close.
- Zombie detection: missed-pong teardown plus a probe ping on
  `visibilitychange` to visible.
- Dashboards segment connection lifetime and reconnect rate by
  platform (mobile vs desktop), alerting on ratio shifts.

## Related

- `documentation/docs/policies/cloudflare/durable-objects-websocket-hibernation.md`
- `documentation/docs/policies/cloudflare/workers-websocket-upgrade.md`
- `documentation/docs/policies/mobile/react-native-netinfo.md`

## Source URLs (verified 2026-08-17)

- Cloudflare WebSockets network settings — https://developers.cloudflare.com/network/websockets/
- WebSocket heartbeat guide (proxy/NAT timeout table, 75% rule) — https://websocket.org/guides/heartbeat/
- WebSocket timeout troubleshooting (cellular NAT, silent drops) — https://websocket.org/guides/troubleshooting/timeout/
- Carrier-grade NAT timeouts on mobile networks — https://blog.wirelessmoves.com/2020/09/carrier-grade-nat-timeouts-and-how-to-configure-your-xmpp-server.html
- Safari drops WebSockets when page not in focus (socket.io #2924) — https://github.com/socketio/socket.io/issues/2924

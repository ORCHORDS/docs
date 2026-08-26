# HTTP/3 / QUIC Irregularities on Mobile Networks (Cloudflare)

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

example project (example.com) mobile users on cellular report intermittent
slow first loads, stalled feed fetches, and dropped R2 media uploads
that desktop users on wired networks never see. The Next.js static
export on Cloudflare Pages and the Worker API (133+ routes) are
identical for both cohorts, D1 queries are fast, and synthetic tests
from the office pass every time. The disparity is protocol-level:
desktop Chrome on ethernet negotiates a stable HTTP/3 connection,
while phones on carrier NAT hit QUIC timeouts, mid-transfer
migration failures during WiFi-to-cellular handoff, and silent
fallback races to HTTP/2 — each adding seconds of dead air or
killing an in-flight multipart upload to R2.

## Context

HTTP/3 runs over QUIC, a UDP-based transport that bundles TLS 1.3,
stream multiplexing, and congestion control. Cloudflare terminates
HTTP/3 at the edge for the client-to-Cloudflare leg only (HTTP/3 to
origin is not supported), so both the Pages site and the Worker API
inherit the zone's HTTP/3 setting. QUIC's headline mobile feature —
connection migration, which lets a connection survive a WiFi to
cellular switch by identifying it with connection IDs instead of the
IP/port 4-tuple — is exactly the part that fails most often in the
wild: carrier-grade NAT (CGNAT), stateful firewalls, and UDP-hostile
middleboxes sit between phones and the edge. Complete UDP/443 blocks
affect an estimated 3-5% of public networks, with corporate and
carrier rates higher, and some ISPs rate-limit high-rate UDP flows
as suspected DDoS traffic. Browsers hide all of this behind silent
fallback to HTTP/2, so the failure shows up as latency, not errors.

## Why QUIC connection migration fails in practice

```
Designed path (RFC 9000 connection migration):

  phone (WiFi 10.0.0.5:51234) ──┐
                                ├──> CF edge matches Connection ID,
  phone (LTE 100.64.3.7:6021) ──┘    connection survives handoff

Real path through carrier infrastructure:

  phone ── CGNAT (rewrites src IP+port ─ middlebox tracking ── CF
            per flow, short UDP timers)   the UDP 4-tuple      edge
                     │                          │
                     ▼                          ▼
    NAT rebinding: new 4-tuple mid-life; ancient/strict boxes drop
    "unknown" UDP flows; QUIC waits on ACKs that never come. UDP
    drops are SILENT — no RST, no ICMP — so the client burns a full
    timeout before reacting. TCP behind the same NAT keeps working.
```

- CGNAT UDP mappings expire fast (often 30-120s idle). A user who
  reads a example project thread then taps "post" resumes on a rebound
  4-tuple; migration only works if every hop tolerates it.
- Middleboxes that key state on the 4-tuple treat the migrated flow
  as a brand-new, half-open UDP stream and drop or rate-limit it.
- Some carriers silently drop UDP/443 outright while TCP/443 is
  fine — the worst case, because nothing signals failure.
- Long R2 uploads are maximally exposed: they hold one connection
  open across the exact window where NAT rebinding happens.

## UDP 443 blocking and the silent HTTP/2 fallback race

```
First visit (no cached Alt-Svc):
  TCP+TLS (HTTP/2) ── works ──> response carries
  alt-svc: h3=":443"; ma=86400   (cached up to 24h)

Later visits: browser races/prefers h3 per cached Alt-Svc
  ├─ UDP OK        → HTTP/3, fast
  ├─ UDP blocked,
  │  fails fast    → fallback to HTTP/2, ~1 RTT penalty
  └─ UDP silently
     dropped       → QUIC retries burn seconds before
                     TCP fallback → "intermittent slow loads"

Chrome falls back to TCP silently, but SKIPS fallback when:
  - its retry attempts are exhausted, or
  - response headers were already delivered (mid-stream death:
    request cannot be replayed → visible failure), or
  - the request wasn't using an alternative service.
```

The mid-stream case is the R2 upload killer: the connection dies
after headers, Chrome cannot transparently replay a partially sent
body, and the upload errors instead of falling back. The Alt-Svc
cache trap compounds it — a phone that cached `h3` on home WiFi
keeps attempting QUIC for up to 24h on a train WiFi that drops UDP.

## Which protocol did real users actually negotiate?

```
Signal                       Where                     Meaning
──────────────────────────────────────────────────────────────────
alt-svc: h3=":443"           curl -sI https://...      zone OFFERS
                                                       HTTP/3 only
Protocol column              DevTools > Network        what THIS
(h3 / h2 / http/1.1)         (right-click headers to   client used
                             enable the column)
ClientRequestProtocol        Logpush http_requests     per-request
                             dataset                   field truth
request.cf.httpProtocol      inside the Worker         per-request,
                             (133 API routes)          loggable
cf-ray                       response header           correlate a
                                                       user report
                                                       to log rows
```

```js
// Worker middleware: emit protocol so Logpush/Analytics Engine
// can split latency and upload failures by negotiated protocol.
export default {
  async fetch(request, env, ctx) {
    const proto = request.cf?.httpProtocol ?? 'unknown'; // "HTTP/3"
    const resp = await handle(request, env);
    ctx.waitUntil(env.METRICS.writeDataPoint({
      blobs: [proto, new URL(request.url).pathname],
      doubles: [resp.ok ? 0 : 1],
      indexes: [proto],
    }));
    return resp;
  },
};
```

If mobile rows skew HTTP/2 while desktop skews HTTP/3 — or mobile
HTTP/3 rows show elevated p95 — the fallback race is confirmed.
`chrome://net-internals/#quic` on a repro device clears cached QUIC
state (clearing normal browser cache is not enough).

## Cloudflare HTTP/3 zone toggle behavior

- Dashboard: Speed > Settings > Protocol Optimization > HTTP/3.
  API: PATCH zone setting `http3` to `"on"` / `"off"`.
- The toggle governs the client-to-edge leg only; edge-to-origin
  never uses HTTP/3. It requires a valid edge certificate.
- Turning it OFF stops advertising Alt-Svc, but clients honor
  cached Alt-Svc for up to `ma` seconds (commonly 86400), so
  expect up to ~24h of stragglers still attempting QUIC.
- Per-hostname disable without touching the zone: a Response Header
  Transform Rule that removes `Alt-Svc` on that hostname forces new
  clients to HTTP/2 — useful to exempt only the upload endpoint:

```
Transform Rule (Response Header Modification)
  When: http.host eq "upload.example.com"
  Then: Remove header "Alt-Svc"
```

## 0-RTT resumption and replay risk

Cloudflare's 0-RTT toggle (Speed settings) lets resuming clients
send the first request before the handshake completes — a real win
on high-RTT cellular, but 0-RTT data has no replay protection and
no forward secrecy. An attacker who captures early data can replay
it. Per RFC 8470, Cloudflare appends `Early-Data: 1` to requests
that arrived as 0-RTT; a non-idempotent handler must reject those
with `425 Too Early` so the client retries after the handshake:

```js
// Worker guard for the 133 API routes: never execute mutations
// (posts, votes, Solana payment intents) from replayable 0-RTT.
if (request.method !== 'GET' &&
    request.headers.get('Early-Data') === '1') {
  return new Response('retry after handshake', { status: 425 });
}
```

## Safari/iOS vs Chrome/Android

```
Browser          HTTP/3 status
──────────────────────────────────────────────────────────────────
Chrome/Edge      On by default since April 2020 (full from ~87);
(Android too)    races QUIC vs TCP, silent HTTP/2 fallback
Safari macOS     Default from Safari 16; partial 16.x-18.1,
                 full 18.5+ — noticeably more conservative:
                 often sticks with HTTP/2 even when h3 offered
Safari iOS       Default from iOS 16; partial 15.6-18.1, full
                 ~17.6+; URLSession apps have their own rules
Firefox          Supported and on by default
```

Consequence: "mobile is slow" is really two populations. Android
Chrome users feel QUIC fallback races and migration failures; iOS
Safari users more often quietly ride HTTP/2 and instead feel plain
TCP/TLS handshake costs on lossy cellular. Segment RUM by OS and
browser before blaming one protocol.

## Anti-patterns

- **Disabling HTTP/3 zone-wide at the first mobile complaint** —
  you lose 1-RTT setup and loss-resilient multiplexing for the
  majority whose networks handle QUIC fine. Measure protocol share
  first; exempt only problem hostnames via Alt-Svc removal.
- **Debugging from office WiFi** — desktop on a clean network never
  reproduces CGNAT rebinding or carrier UDP throttling. Repro on a
  real phone on real cellular, or at least behind a UDP-dropping
  firewall rule.
- **Enabling 0-RTT with no `Early-Data` handling** — replayable
  POSTs on an anonymous platform with Solana payments means
  duplicate mutations and double-spends. Gate non-idempotent
  routes with 425 first.
- **Trusting synthetic checks that pin the protocol** — a curl
  `--http3` probe proves the edge speaks h3; it says nothing about
  what carrier-NATted users negotiate. Only field data
  (ClientRequestProtocol / request.cf.httpProtocol) does.

## Gotchas

- UDP failures are silent by design of the broken networks: no
  RST, no ICMP unreachable. The cost is a full QUIC timeout, which
  users read as "the app hung", not "the app errored".
- Alt-Svc is cached up to 24h (`ma=86400`), so any server-side
  HTTP/3 change — on or off — rolls out to returning clients over
  a full day. Don't judge a toggle flip by the next 10 minutes.
- Chrome cannot silently fall back once response headers arrived;
  mid-stream QUIC death surfaces as a failed request. Make R2
  multipart uploads small-parted and resumable so a killed part
  retries instead of restarting the whole file.
- The HTTP/3 toggle never affects Worker-to-R2/D1/origin traffic,
  and `chrome://net-internals/#quic` is the only way to clear
  cached QUIC state — normal cache clearing does not touch it.

## Verification

- Logpush http_requests dataset (or Analytics Engine datapoints)
  includes ClientRequestProtocol, segmented by device type and OS.
- Protocol mix dashboards show h3 share for mobile vs desktop, and
  p95 latency per protocol per cohort.
- `curl -sI https://example.com | grep -i alt-svc` shows
  `h3=":443"` exactly on hostnames where HTTP/3 is intended.
- All non-GET Worker routes reject `Early-Data: 1` with 425 before
  any state change (see the 0-RTT guard above).
- R2 uploads use multipart with per-part retry; a dropped part on
  cellular resumes instead of failing the upload.
- A cellular repro checklist exists: DevTools protocol column,
  net-internals QUIC reset, WiFi-to-LTE handoff mid-upload.

## Related

- `documentation/docs/policies/cloudflare/workers-streaming-responses.md`
- `documentation/docs/policies/cloudflare/r2-multipart-upload.md`
- `documentation/docs/policies/performance/cdn-cache-strategy.md`
- `documentation/docs/policies/security/tls-13-early-data-0rtt-replay-safe-endpoint-policy.md`

## Source URLs (verified 2026-08-17)

- Enable HTTP/3 (Cloudflare Speed docs) — https://developers.cloudflare.com/speed/optimization/protocol/http3/
- Troubleshoot protocol issues (Cloudflare) — https://developers.cloudflare.com/speed/optimization/protocol/troubleshooting/protocol-troubleshooting/
- HTTP requests Logpush dataset fields — https://developers.cloudflare.com/logs/logpush/logpush-job/datasets/zone/http_requests/
- RFC 8470: Using Early Data in HTTP — https://datatracker.ietf.org/doc/html/rfc8470
- QUIC: The Protocol That Breaks Your Site Without Warning — https://andrewbaker.ninja/2026/05/02/quic-the-protocol-that-breaks-your-site-without-warning/

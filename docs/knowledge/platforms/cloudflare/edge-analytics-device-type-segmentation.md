# Edge Analytics Device-Type Segmentation: Making Mobile Skew Visible

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Aggregate dashboards look healthy — 0.4% error rate, 92% cache hit
ratio, p95 under 300ms — while mobile users report a broken app.
On example project (example.com, Worker API with 133+ routes) every major
irregularity was invisible in the aggregate view: Turnstile
challenge loops hit only in-app WebViews, stale assets only iOS
WebKit, CGNAT 429s only mobile carrier ASNs, QUIC-fallback latency
only Android on flaky radios. Desktop traffic averaged the pain
away. You cannot fix a skew you never segment — and by default,
nothing at the edge segments by device for you.

## Context

Cloudflare carries device/platform signal in four places: Logpush
HTTP request fields, GraphQL Analytics API dimensions, Web Analytics
(RUM) breakdowns, and — most flexibly — Workers Analytics Engine
(WAE) datapoints you write yourself. The first three give you
Cloudflare's own device classification; only WAE lets you attach a
platform label matching *your* traffic taxonomy (splitting "mobile"
into ios-webkit vs android-chrome vs in-app WebView vs native app).
example project standard practice: every WAE datapoint the Worker writes
includes a normalized platform blob, parsed once at the edge.
This entry covers where the signal lives and the queries that
surface disproportion; WAE basics: `workers-analytics-engine.md`.

## Where device signal lives

```
Dataset                 Device/platform signal
──────────────────────────────────────────────────────────────────
Logpush http_requests   ClientRequestUserAgent (raw UA string)
                        ClientDeviceType (CF's device class)
                        ClientRequestProtocol (HTTP/1.1|2|3)
                        BotScore + BotScoreSrc (Bot Mgmt only)
                        ClientCountry, ClientASN
                        CacheCacheStatus, EdgeResponseStatus,
                        OriginResponseStatus

GraphQL Analytics       httpRequestsAdaptiveGroups dimensions:
(zone-level)            clientDeviceType, userAgentBrowser,
                        userAgentOS, clientCountryName,
                        edgeResponseStatus, clientRequestPath

Web Analytics (RUM)     Dimensions: Device type (desktop/mobile/
                        tablet), Browser, Operating system,
                        Country, Path, plus "Exclude bots" toggle

WAE (custom)            Whatever blobs you write — your own
                        normalized platform label, app version,
                        route group, colo, protocol
──────────────────────────────────────────────────────────────────
Logpush/GraphQL = zone-wide truth; RUM = browser-side CWV by
device; WAE = API-route-level platform cuts.
```

`ClientDeviceType` and GraphQL's `clientDeviceType` are CF's
coarse desktop/mobile/tablet classification — good for a first
cut, useless for separating in-app WebViews from mobile Safari.

## Normalize platform once, at the edge

Parse the UA a single time per request into a small closed set of
labels. Ordered heuristics beat a full ua-parser library here
because you control the taxonomy:

```typescript
// platform.ts — example project normalized platform taxonomy
export type Platform =
  | 'ios-webkit' | 'android-chrome' | 'in-app'
  | 'desktop' | 'native-app' | 'bot';

export function classifyPlatform(req: Request): Platform {
  const ua = req.headers.get('user-agent') ?? '';
  if (ua.startsWith('example project/')) return 'native-app';  // own client
  if (/bot|crawl|spider|curl|python-requests/i.test(ua))
    return 'bot';
  // In-app WebViews: embed markers, or Android's "; wv)" token
  if (/Instagram|FBAN|FBAV|TikTok|Line\/|; wv\)/.test(ua))
    return 'in-app';
  if (/iPhone|iPad|iPod/.test(ua)) return 'ios-webkit';
  if (/Android/.test(ua)) return 'android-chrome';
  return 'desktop';
}
```

Then every WAE datapoint carries it in a fixed blob position:

```typescript
const platform = classifyPlatform(request);
env.ANALYTICS.writeDataPoint({
  indexes: [routeGroup],           // e.g. 'auth', 'feed', 'media'
  blobs: [
    platform,                      // blob1 — ALWAYS platform
    String(response.status),       // blob2
    request.cf?.httpProtocol ?? '',// blob3 — 'HTTP/2', 'HTTP/3'
    request.cf?.country ?? 'XX',   // blob4
    String(request.cf?.asn ?? 0),  // blob5
  ],
  doubles: [durationMs],           // double1
});
```

Pin blob positions in a shared constant — queries reference
`blob1`, not names, and a reshuffle silently corrupts dashboards.

## Recipes: disproportion queries

Error rate by platform (WAE SQL API, sampling-aware — see Gotchas):

```sql
SELECT blob1 AS platform,
  sum(_sample_interval) AS requests,
  sum(if(blob2 >= '500' OR blob2 = '499', _sample_interval, 0))
    / sum(_sample_interval) AS error_rate
FROM example project_api_events
WHERE timestamp > NOW() - INTERVAL '1' HOUR
GROUP BY platform ORDER BY error_rate DESC
```

p50/p95 latency by platform and protocol (QUIC fallback shows up
as an HTTP/3-vs-HTTP/2 gap that exists only on mobile rows):

```sql
SELECT blob1 AS platform, blob3 AS proto,
  quantileExactWeighted(0.50)(double1, _sample_interval) AS p50,
  quantileExactWeighted(0.95)(double1, _sample_interval) AS p95
FROM example project_api_events
WHERE timestamp > NOW() - INTERVAL '6' HOUR
GROUP BY platform, proto
```

Challenge/403 rate and cache hit ratio by device class, zone-wide
(GraphQL, no Worker changes needed):

```graphql
{
  viewer {
    zones(filter: { zoneTag: $zoneTag }) {
      httpRequestsAdaptiveGroups(
        filter: { datetime_geq: $start, datetime_lt: $end }
        limit: 100
      ) {
        count
        dimensions {
          clientDeviceType     # desktop | mobile | tablet
          edgeResponseStatus   # 403 spike = challenge skew
          cacheStatus
        }
      }
    }
  }
}
```

Compute per-device ratios client-side: `403s / total` and
`hit / (hit + miss + expired)` per `clientDeviceType`. This is how
the example project WebView challenge-loop and iOS stale-asset incidents
finally became visible.

## Alert on divergence, not aggregates

An aggregate error-rate alert at 2% never fires when 6% of mobile
requests fail inside mostly-healthy desktop traffic. Alert on the
ratio between segments instead:

```
fire when:
  mobile_error_rate > 3 x desktop_error_rate
  AND mobile_requests > 500        # volume floor kills flapping
sustained for 2 consecutive 5-min windows
```

Implement as a Worker cron: query the WAE SQL API, compare
segments, notify. The volume floor matters — low-traffic platforms
produce wild ratios from tiny samples. Same pattern for challenge
rate and cache hit ratio (mobile more than 15pp below desktop).

## Anti-patterns

- **Segmenting only after an incident** — the platform blob costs
  one slot and ~zero CPU; retro-segmenting old data is impossible.
- **Parsing the UA per query instead of per request** — raw UA
  strings in blobs blow the 512-byte-value budget, explode
  cardinality, and force every dashboard to re-implement parsing.
  Normalize once at the edge into a closed label set.
- **Treating "mobile" as one segment** — CF's desktop/mobile/
  tablet split hides the real offenders. In-app WebViews and
  native apps behave nothing like mobile Safari; label them.
- **Alerting on aggregate rates** — any threshold loose enough
  to survive desktop noise is too loose to catch a mobile-only
  regression. Alert on segment ratios with volume floors.
- **Importing a full ua-parser build into the Worker** — for a
  six-label taxonomy, ordered heuristics are faster and easier to
  test. Reserve real parsers for offline Logpush enrichment.

## Gotchas

- **GraphQL adaptive datasets are sampled** — nodes with
  "Adaptive" in the name use ABR sampling; long ranges return
  higher sample intervals, so small segments wobble. Use
  confidence-interval fields where exposed and widen the window
  before trusting a small-segment ratio.
- **WAE samples at write AND read time** — high-volume indexes
  get sampled on ingest; ABR kicks in on long-range reads. Plain
  `count()` undercounts: use `sum(_sample_interval)`, weight sums
  by `_sample_interval`, and use `quantileExactWeighted(...,
  _sample_interval)` for percentiles. `_sample_interval` varies
  per row — never multiply by a constant.
- **UA reduction erodes UA fidelity** — Chrome's reduced UA
  freezes Android device model and minor versions. Low-entropy
  Client Hints (`Sec-CH-UA-Mobile`, `Sec-CH-UA-Platform`) arrive
  by default on Chromium; high-entropy ones (`Sec-CH-UA-Model`)
  need an `Accept-CH` opt-in and only arrive on later requests —
  and Safari/WebKit sends no UA-CH at all. Keep the taxonomy
  coarse enough to survive this.
- **`BotScore`/`BotScoreSrc` are entitlement-gated** — Logpush
  emits them only for Bot Management customers. Without them,
  fall back to the heuristic `bot` label and verified-bot flags.
- **Index choice drives WAE sampling** — equitable sampling keeps
  per-index-value volume roughly equal. Indexing by route group
  means a mobile flood cannot starve desktop rows, but platform
  counts inside a hot route get sampled harder — the
  sampling-aware aggregates above stay correct either way.

## Verification

- Every WAE datapoint carries a normalized platform label in a
  fixed blob position (blob1), from a shared classifier module.
- Classifier unit-tested against real UAs: iOS Safari, Android
  Chrome, in-app WebViews, native app, bots, reduced-UA Chrome.
- Dashboards show error rate, p95 latency, challenge rate, and
  cache hit ratio **by platform**, never only in aggregate.
- WAE queries use `sum(_sample_interval)` and
  `quantileExactWeighted`; none use bare `count()`.
- Divergence alert (mobile vs desktop error-rate ratio with
  volume floor) fires in a staged test before it is trusted.
- GraphQL `clientDeviceType` breakdown cross-checked against WAE
  platform labels monthly — drift means classifier rot.

## Related

- `documentation/docs/policies/cloudflare/workers-analytics-engine.md`
- `documentation/docs/policies/cloudflare/cache-device-type-segmentation-mobile-desktop.md`
- `documentation/docs/policies/monitoring/structured-logging-json-correlation.md`
- `documentation/docs/policies/performance/core-web-vitals-mobile-desktop-disparity-edge-caching.md`

## Source URLs (verified 2026-08-17)

- Logpush HTTP requests dataset fields — https://developers.cloudflare.com/logs/logpush/logpush-job/datasets/zone/http_requests/
- Web Analytics dimensions — https://developers.cloudflare.com/web-analytics/data-metrics/dimensions
- Sampling with Workers Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/sampling/
- Understanding sampling in Cloudflare Analytics — https://developers.cloudflare.com/analytics/sampling/
- Privacy Sandbox: User-Agent reduction — https://privacysandbox.google.com/protections/user-agent

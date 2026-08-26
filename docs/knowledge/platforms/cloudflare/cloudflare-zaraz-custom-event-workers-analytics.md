# Cloudflare Zaraz Custom Event Workers Analytics

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case
example project / example.com runs as an anonymous social platform where users cannot be tracked with traditional third-party analytics cookies. The platform needs privacy-first behavioral analytics — page views, content engagement, and feature usage — without loading Google Analytics or similar SDKs that trigger browser ITP/ETP blocking. Cloudflare Zaraz provides a server-side tag management layer that fires analytics tools from the edge, eliminating client-side tracking JavaScript and enabling Workers to inject custom event data before tags fire.

## Context
Cloudflare Zaraz is a server-side tag manager embedded in Cloudflare's edge. Events triggered from the client via `zaraz.track()` or `zaraz.ecommerce()` are received by Zaraz on the edge, where they are enriched, transformed via Zaraz Actions, and forwarded to configured tools (GA4, Amplitude, custom webhooks, etc.). Workers can interact with Zaraz through the `zaraz` context object in Worker scripts, allowing server-side event injection and per-request data layer manipulation without any client JavaScript.

## Enabling Zaraz and Configuring the Worker Integration

Zaraz is enabled per-zone in the Cloudflare dashboard (Speed → Zaraz). Once enabled, the `zaraz` object is available inside Workers that handle requests for the zone:

```toml
# wrangler.toml — the edge analytics Worker
name = "example project-analytics-layer"
main = "src/index.ts"
compatibility_date = "2025-01-01"

# Zaraz is a zone-level feature; no explicit binding needed in wrangler.toml
# The `zaraz` context is injected by the runtime when Zaraz is enabled on the zone

[[d1_databases]]
binding = "DB"
database_name = "example project-prod"
database_id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxx"

[vars]
ZARAZ_DATASET = "example project-production"
```

Configure in the Zaraz dashboard:
- Create a **Custom HTML Tool** or **HTTP Request Tool** as the Zaraz endpoint
- Under **Triggers**, add `Custom Event — name equals *` to catch all custom events
- Under **Actions**, map Zaraz event properties to your analytics tool's fields

## Client-Side Event Emission (Minimal SDK)

example project loads no third-party tracking JavaScript. Zaraz's own lightweight snippet (`zaraz.js`, ~3KB, served by Cloudflare) is the only external script:

```typescript
// client/analytics.ts — TypeScript client helper
declare global {
  interface Window {
    zaraz?: {
      track: (eventName: string, properties?: Record<string, unknown>) => void;
      ecommerce: (eventName: string, properties?: Record<string, unknown>) => void;
      set: (key: string, value: string) => void;
    };
  }
}

export function trackEvent(
  name: string,
  properties: Record<string, unknown> = {}
): void {
  if (typeof window === "undefined" || !window.zaraz) return;
  window.zaraz.track(name, {
    ...properties,
    platform: "example project",
    ts: Date.now(),
  });
}

// Usage examples in UI components:
// trackEvent("post_view", { post_id: "abc123", category: "meme" });
// trackEvent("reaction_press", { reaction: "fire", post_id: "abc123" });
// trackEvent("share_tap", { post_id: "abc123", channel: "link" });
```

Zaraz intercepts the `zaraz.track()` call and forwards the event to the edge without the browser ever connecting to a third-party analytics domain.

## Server-Side Event Injection via Workers zaraz Context

Workers can programmatically fire Zaraz events server-side for actions that don't originate from the browser — API calls, background jobs, server-generated feeds:

```typescript
// src/index.ts — Worker with Zaraz server-side event injection
export interface Env {
  DB: D1Database;
}

// Zaraz context type (from @cloudflare/workers-types)
interface ZarazContext {
  track: (
    name: string,
    properties?: Record<string, unknown>
  ) => Promise<void>;
}

declare global {
  const zaraz: ZarazContext | undefined;
}

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(req.url);

    // Server-side: track API-driven post views (e.g., from RSS or share links)
    if (url.pathname.startsWith("/api/posts/") && req.method === "GET") {
      const postId = url.pathname.split("/")[3];
      const cf = req.cf as CfProperties | undefined;

      // Non-blocking Zaraz server-side event
      ctx.waitUntil(
        zaraz?.track("api_post_view", {
          post_id: postId,
          source: req.headers.get("Referer") ?? "direct",
          country: cf?.country ?? "XX",
          device_type: cf?.deviceType ?? "unknown",
          bot_score: (cf?.botManagement as any)?.score ?? null,
        }) ?? Promise.resolve()
      );

      // Continue to serve the actual API response
      const post = await env.DB.prepare(
        "SELECT * FROM posts WHERE id = ? AND deleted_at IS NULL"
      )
        .bind(postId)
        .first();

      if (!post) return new Response("Not found", { status: 404 });
      return Response.json(post);
    }

    return new Response("Not found", { status: 404 });
  },
};
```

## Zaraz Actions: Transforming Events Before Tool Dispatch

Zaraz Actions run on the edge before forwarding events to tools. Use them to enrich, filter, or remap event data without touching your Worker code:

```javascript
// Zaraz Action (configured in dashboard — "JavaScript Action" type)
// This runs on the edge for every event that matches the "post_view" trigger

const postId = client.__zarazTrack === "post_view" ? client.post_id : null;

if (!postId) return; // Drop events without a post_id

// Enrich with computed properties
zarazEvent.category = postId.startsWith("v") ? "video" : "image";
zarazEvent.hour_of_day = new Date().getUTCHours();

// Forward to HTTP Request tool (custom analytics endpoint)
// The tool is configured to POST to https://analytics.example.com/ingest
```

Zaraz Actions use a JavaScript sandbox — they can read `client.*` (the event payload), modify `zarazEvent.*` (what gets forwarded), and call built-in Zaraz helpers, but cannot make `fetch()` calls directly.

## Custom HTTP Endpoint Tool: Forwarding to Workers Analytics Engine

Configure a Zaraz **HTTP Request Tool** to POST events to a Worker that writes to Analytics Engine:

```typescript
// src/zaraz-receiver.ts — receives Zaraz HTTP Tool POSTs
export interface ReceiverEnv {
  ANALYTICS: AnalyticsEngineDataset;
}

interface ZarazHttpPayload {
  event: string;
  post_id?: string;
  country?: string;
  category?: string;
  hour_of_day?: number;
  bot_score?: number;
}

export default {
  async fetch(req: Request, env: ReceiverEnv): Promise<Response> {
    if (req.method !== "POST") return new Response("", { status: 405 });

    const payload = await req.json<ZarazHttpPayload>();

    env.ANALYTICS.writeDataPoint({
      blobs: [
        payload.event,
        payload.post_id ?? "",
        payload.country ?? "XX",
        payload.category ?? "unknown",
      ],
      doubles: [
        payload.hour_of_day ?? 0,
        payload.bot_score ?? 99,
      ],
      indexes: [payload.event],
    });

    return new Response(null, { status: 204 });
  },
};
```

```toml
# wrangler.toml additions for the receiver Worker
[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "example project_zaraz_events"
```

Query in the dashboard: **Analytics Engine → SQL API**:
```sql
SELECT
  blob1 AS event,
  blob3 AS country,
  count() AS total,
  SUM(_sample_interval) AS estimated_total
FROM example project_zaraz_events
WHERE timestamp > NOW() - INTERVAL '1' HOUR
GROUP BY event, country
ORDER BY estimated_total DESC
```

## Anti-patterns
- Using `zaraz.track()` for sensitive actions (login, purchase, private content view) without stripping PII from the payload — Zaraz logs raw event properties in the dashboard
- Relying on Zaraz for real-time alerting — Zaraz event delivery to HTTP tools has 1–5 second edge latency plus tool processing; use Durable Objects for real-time signals
- Configuring more than 3–4 tool dispatches per event — each tool call adds latency to the Zaraz processing chain on the edge
- Setting `zaraz.set()` with user identifiers across sessions — violates Zaraz's privacy model and GDPR Article 5 data minimization
- Loading the Zaraz snippet asynchronously as an afterthought — it must be in `<head>` before other scripts to intercept early events

## Gotchas
- The `zaraz` global in Workers is only available when the Worker is deployed to the zone where Zaraz is enabled; it is `undefined` in `wrangler dev --local`
- Zaraz Actions execute in a sandboxed JavaScript environment that is NOT the standard Workers runtime — `fetch()`, `crypto`, and `Response` are not available
- The Zaraz HTTP Tool POST body is JSON but the exact schema depends on your Zaraz tool configuration — log incoming payloads to understand the actual shape before building the receiver
- `zaraz.track()` calls from Workers are fire-and-forget — errors are not surfaced to the Worker; check Zaraz logs in the dashboard for delivery failures
- Zaraz is bypassed on `Cache-Control: no-store` responses by default — ensure your API responses do not incorrectly set this header if you need server-side Zaraz events

## Verification
1. Enable Zaraz on the zone (Speed → Zaraz → Enable)
2. Add the Zaraz snippet to the SPA `<head>` (Zaraz auto-injects it via the zone proxy if enabled)
3. Open DevTools → Network and confirm `zaraz.js` loads from `static.cloudflareinsights.com`
4. Fire a test event: `window.zaraz.track("test_event", { source: "devtools" })` in the browser console
5. Check Zaraz dashboard (Speed → Zaraz → History) for the event
6. Deploy the receiver Worker and confirm Analytics Engine rows: `npx wrangler analytics-engine query --dataset example project_zaraz_events`

## Related
- `zaraz-third-party-tags-mobile-cpu.md`
- `cloudflare-workers-analytics-engine-custom-metrics.md`
- `cloudflare-web-analytics-privacy-first.md`
- `workers-analytics-engine.md`
- `workers-analytics-engine-graphql-api-querying.md`

## Sources
- https://developers.cloudflare.com/zaraz/
- https://developers.cloudflare.com/zaraz/get-started/
- https://developers.cloudflare.com/zaraz/web-api/track/
- https://developers.cloudflare.com/zaraz/advanced/workers/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/zaraz/reference/actions/

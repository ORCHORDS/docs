# Cloudflare Page Shield Script Inventory via Workers API

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
Your security team needs an automated pipeline that pulls the Page Shield JavaScript inventory for a zone, detects newly added third-party scripts or policy violations, and alerts via webhook — all without manual dashboard review.

## Context
Page Shield monitors every script loaded by browsers visiting your zone and classifies them by host, first-seen date, and malicious-content signals. The Cloudflare REST API (`/client/v4/zones/{zone_id}/page_shield/scripts`) exposes this inventory programmatically. A scheduled Worker can diff the current script list against a snapshot stored in KV, emit alerts for new or high-risk scripts, and optionally enforce a Content-Security-Policy (CSP) blocklist by writing a Worker that rewrites response headers.

## API Token & Configuration

`wrangler.toml`:
```toml
name = "page-shield-monitor"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[vars]
ZONE_ID = "<your-zone-id>"
ALERT_WEBHOOK = "https://hooks.example.com/security-alerts"

[[kv_namespaces]]
binding = "SHIELD_STATE"
id = "<kv-namespace-id>"

[triggers]
crons = ["0 * * * *"]   # hourly scan

# Set secret: wrangler secret put CF_API_TOKEN
# Required permissions: Page Shield Read, Zone Read
```

## Page Shield API Client

```typescript
// src/page-shield-api.ts
export interface PageShieldScript {
  id: string;
  url: string;
  host: string;
  domain_reported_malicious: boolean;
  url_contains_cdn_cgi_path: boolean;
  first_seen_at: string;
  last_seen_at: string;
  status: "active" | "inactive";
  fetched_at: string | null;
  page_urls: string[];
  url_reported_malicious: boolean;
  malicious_url: boolean;
  js_integrity_score: number | null; // 1 (bad) – 100 (clean), null = not yet scanned
}

interface PageShieldResponse {
  result: PageShieldScript[];
  result_info: { count: number; page: number; per_page: number; total_count: number };
  success: boolean;
}

export async function listAllScripts(
  zoneId: string,
  token: string
): Promise<PageShieldScript[]> {
  const perPage = 100;
  let page = 1;
  const all: PageShieldScript[] = [];

  while (true) {
    const url = `https://api.cloudflare.com/client/v4/zones/${zoneId}/page_shield/scripts` +
      `?per_page=${perPage}&page=${page}&order_by=last_seen_at&direction=desc`;

    const res = await fetch(url, {
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
    });

    if (!res.ok) {
      throw new Error(`Page Shield API error: ${res.status} ${await res.text()}`);
    }

    const body = (await res.json()) as PageShieldResponse;
    all.push(...body.result);

    if (all.length >= body.result_info.total_count) break;
    page++;
  }

  return all;
}

export async function getScript(
  zoneId: string,
  scriptId: string,
  token: string
): Promise<PageShieldScript | null> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${zoneId}/page_shield/scripts/${scriptId}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  if (!res.ok) return null;
  const body = (await res.json()) as { result: PageShieldScript; success: boolean };
  return body.success ? body.result : null;
}
```

## Diff & Alert Worker

```typescript
// src/index.ts
import { listAllScripts, type PageShieldScript } from "./page-shield-api";

export interface Env {
  SHIELD_STATE: KVNamespace;
  CF_API_TOKEN: string;
  ZONE_ID: string;
  ALERT_WEBHOOK: string;
}

interface ScriptSnapshot {
  ids: string[];       // set of script IDs seen in previous scan
  updatedAt: string;
}

interface AlertPayload {
  type: "new_script" | "malicious_script" | "low_integrity";
  script: Pick<PageShieldScript, "id" | "url" | "host" | "first_seen_at" | "js_integrity_score" | "malicious_url">;
  zoneId: string;
  detectedAt: string;
}

async function sendAlert(webhook: string, payload: AlertPayload): Promise<void> {
  await fetch(webhook, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

function isHighRisk(script: PageShieldScript): boolean {
  return (
    script.malicious_url ||
    script.domain_reported_malicious ||
    script.url_reported_malicious ||
    (script.js_integrity_score !== null && script.js_integrity_score < 40)
  );
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const now = new Date().toISOString();

    // Load previous snapshot
    const snapshot = await env.SHIELD_STATE.get<ScriptSnapshot>("script-snapshot", "json");
    const knownIds = new Set(snapshot?.ids ?? []);

    // Fetch current inventory
    const scripts = await listAllScripts(env.ZONE_ID, env.CF_API_TOKEN);
    const currentIds = scripts.map((s) => s.id);

    // Detect new scripts
    const newScripts = scripts.filter((s) => !knownIds.has(s.id));
    // Detect high-risk scripts (new or existing)
    const highRiskScripts = scripts.filter(isHighRisk);

    const alerts: Promise<void>[] = [];

    for (const script of newScripts) {
      alerts.push(
        sendAlert(env.ALERT_WEBHOOK, {
          type: "new_script",
          script: {
            id: script.id,
            url: script.url,
            host: script.host,
            first_seen_at: script.first_seen_at,
            js_integrity_score: script.js_integrity_score,
            malicious_url: script.malicious_url,
          },
          zoneId: env.ZONE_ID,
          detectedAt: now,
        })
      );
    }

    for (const script of highRiskScripts) {
      alerts.push(
        sendAlert(env.ALERT_WEBHOOK, {
          type: script.malicious_url ? "malicious_script" : "low_integrity",
          script: {
            id: script.id,
            url: script.url,
            host: script.host,
            first_seen_at: script.first_seen_at,
            js_integrity_score: script.js_integrity_score,
            malicious_url: script.malicious_url,
          },
          zoneId: env.ZONE_ID,
          detectedAt: now,
        })
      );
    }

    ctx.waitUntil(Promise.allSettled(alerts));

    // Persist new snapshot
    await env.SHIELD_STATE.put(
      "script-snapshot",
      JSON.stringify({ ids: currentIds, updatedAt: now } satisfies ScriptSnapshot)
    );

    console.log(
      `Page Shield scan complete: ${scripts.length} scripts, ` +
      `${newScripts.length} new, ${highRiskScripts.length} high-risk`
    );
  },
} satisfies ExportedHandler<Env>;
```

## CSP Enforcement via Workers Header Rewrite

```typescript
// A separate Worker (or same Worker on fetch) that enforces an allowlist-based CSP
const ALLOWED_SCRIPT_HOSTS = [
  "cdn.yourapp.com",
  "www.googletagmanager.com",
  "static.cloudflareinsights.com",
];

function buildCSP(nonce: string): string {
  const scriptSrc = [
    `'nonce-${nonce}'`,
    "'strict-dynamic'",
    ...ALLOWED_SCRIPT_HOSTS.map((h) => `https://${h}`),
  ].join(" ");

  return [
    `script-src ${scriptSrc}`,
    "object-src 'none'",
    "base-uri 'self'",
  ].join("; ");
}

export async function applyCSP(req: Request, upstream: Fetcher): Promise<Response> {
  const nonce = crypto.randomUUID().replace(/-/g, "");
  const res = await upstream.fetch(req);

  const newHeaders = new Headers(res.headers);
  newHeaders.set("Content-Security-Policy", buildCSP(nonce));
  // Expose nonce for server-rendered script tags via a header
  newHeaders.set("X-CSP-Nonce", nonce);

  return new Response(res.body, { status: res.status, headers: newHeaders });
}
```

## Anti-patterns
- **Only scanning once a day** — Page Shield can detect a new script within minutes of it being injected; hourly or more frequent scanning limits dwell time.
- **Alerting on every script unconditionally** — `js_integrity_score` and `malicious_url` narrow alerts to actionable signals; noise causes alert fatigue.
- **Using a zone-scoped token with broad write permissions** — Page Shield monitoring needs only `Page Shield:Read` and `Zone:Read`; never over-scope secrets.
- **Storing the full script list in KV** — KV values cap at 25 MB; store only IDs (or a hash set) to stay well within limits.
- **Blocking scripts in the CSP before verifying with your dev team** — a new CDN host added by a developer looks identical to a supply-chain attack in the inventory; always alert before blocking.

## Gotchas
- `js_integrity_score` is `null` until Cloudflare's crawler fetches the script (may take up to 24 hours after first detection).
- The Page Shield API requires a **Business** or **Enterprise** plan; the endpoint returns 403 on Pro and below.
- `page_urls` is capped at 25 sample URLs per script even if the script appears on thousands of pages.
- Scripts behind authenticated pages are never seen by Page Shield because Cloudflare's crawler cannot log in.
- Cron Worker CPU time counts toward the zone's Worker invocation limits — keep the scan logic efficient; paginated fetches run serially to avoid rate-limit collisions.

## Verification
1. `npx wrangler deploy` then `npx wrangler cron trigger page-shield-monitor` to fire the scheduled event immediately.
2. Manually load a page on your zone with a new `<script src>` and wait up to 10 minutes; re-trigger the cron and confirm the webhook fires with `type: "new_script"`.
3. Inspect `SHIELD_STATE` KV key `script-snapshot` to verify `ids` array is populated and `updatedAt` is recent.
4. Call the API directly: `curl -H "Authorization: Bearer $CF_API_TOKEN" "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/page_shield/scripts?per_page=1"` to confirm token permissions.

## Related
- `cloudflare-snippets-edge-javascript.md`
- `csp-headers-and-cf-waf.md`
- `zaraz-third-party-tags-mobile-cpu.md`
- `workers-tail-workers.md`
- `cloudflare-workers-secrets-store-rotation-automation.md`

## Sources
- https://developers.cloudflare.com/page-shield/
- https://developers.cloudflare.com/page-shield/reference/page-shield-api/
- https://developers.cloudflare.com/page-shield/use-cases/detect-malicious-scripts/

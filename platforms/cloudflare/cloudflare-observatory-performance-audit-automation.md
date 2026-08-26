# Cloudflare Observatory Performance Audit Automation

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your team ships frequently and wants continuous Lighthouse scores tracked per
deployment without manually opening the Cloudflare dashboard.  You need to
trigger Observatory audits programmatically, retrieve scores, and gate CI/CD
pipelines or send Slack alerts when Core Web Vitals regress.

---

## Context

Cloudflare Observatory wraps Google Lighthouse and runs it from Cloudflare's
global network, storing results per zone.  Every audit is tied to a URL and a
region; results include the Lighthouse JSON report plus individual scores for
Performance, Accessibility, Best Practices, and SEO.

The Observatory REST API lives under the Speed endpoint family:

```
https://api.cloudflare.com/client/v4/zones/{zone_id}/speed_api/pages/{url}/tests
```

Authentication uses the standard `Authorization: Bearer <token>` header with
an API token that carries the `Zone.Speed` (edit) permission.

Key concepts:

- **Test** — a single Lighthouse run for one URL and one region.
- **Schedule** — automatic re-testing on a cadence (daily, weekly).
- **Trend** — historical score series for a URL.
- **Region** — Cloudflare PoP from which the test originates
  (e.g. `us-central1`, `europe-west1`).

---

## Triggering an Audit from a Worker (CI Webhook Pattern)

A lightweight Worker receives a POST from your CI system after a deployment,
fires the Observatory test, and polls until it completes.

```typescript
// src/index.ts
export interface Env {
  CF_API_TOKEN: string; // Observatory-scoped API token (secret)
  CF_ZONE_ID: string;   // target zone (var)
  SLACK_WEBHOOK: string; // optional alert sink (secret)
}

const CF_API = "https://api.cloudflare.com/client/v4";

interface ObservatoryTest {
  id: string;
  url: string;
  region: string;
  status: "Pending" | "Running" | "Complete" | "Failed";
  scheduleFrequency?: string;
  lighthouse?: {
    categories: {
      performance: { score: number };
      accessibility: { score: number };
      "best-practices": { score: number };
      seo: { score: number };
    };
  };
}

async function triggerTest(
  zoneId: string,
  token: string,
  pageUrl: string,
  region = "us-central1",
): Promise<ObservatoryTest> {
  const res = await fetch(
    `${CF_API}/zones/${zoneId}/speed_api/pages/${encodeURIComponent(pageUrl)}/tests`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ region }),
    },
  );
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Observatory trigger failed: ${res.status} ${err}`);
  }
  const { result } = (await res.json()) as { result: ObservatoryTest };
  return result;
}

async function pollTest(
  zoneId: string,
  token: string,
  pageUrl: string,
  testId: string,
  maxWaitMs = 120_000,
): Promise<ObservatoryTest> {
  const deadline = Date.now() + maxWaitMs;
  while (Date.now() < deadline) {
    const res = await fetch(
      `${CF_API}/zones/${zoneId}/speed_api/pages/${encodeURIComponent(pageUrl)}/tests/${testId}`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const { result } = (await res.json()) as { result: ObservatoryTest };
    if (result.status === "Complete" || result.status === "Failed") {
      return result;
    }
    // Observatory tests typically complete within 30-60 s
    await new Promise((r) => setTimeout(r, 5_000));
  }
  throw new Error("Observatory test timed out");
}

async function postSlack(webhook: string, message: string): Promise<void> {
  await fetch(webhook, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: message }),
  });
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const body = (await request.json()) as { url: string; region?: string };
    const { url: pageUrl, region } = body;
    if (!pageUrl) {
      return new Response(JSON.stringify({ error: "url required" }), { status: 400 });
    }

    // Fire-and-forget the full audit so CI webhook responds quickly
    ctx.waitUntil(
      (async () => {
        const test = await triggerTest(env.CF_ZONE_ID, env.CF_API_TOKEN, pageUrl, region);
        const completed = await pollTest(
          env.CF_ZONE_ID,
          env.CF_API_TOKEN,
          pageUrl,
          test.id,
        );

        if (completed.status === "Failed" || !completed.lighthouse) {
          await postSlack(env.SLACK_WEBHOOK, `⚠️ Observatory test FAILED for ${pageUrl}`);
          return;
        }

        const scores = completed.lighthouse.categories;
        const perf = Math.round(scores.performance.score * 100);
        const a11y = Math.round(scores.accessibility.score * 100);

        const passing = perf >= 80 && a11y >= 90;
        const emoji = passing ? "✅" : "🚨";
        const msg =
          `${emoji} Observatory for *${pageUrl}* (${completed.region})\n` +
          `Performance: ${perf}  Accessibility: ${a11y}  ` +
          `Best Practices: ${Math.round(scores["best-practices"].score * 100)}  ` +
          `SEO: ${Math.round(scores.seo.score * 100)}`;

        await postSlack(env.SLACK_WEBHOOK, msg);
      })(),
    );

    return new Response(JSON.stringify({ status: "triggered" }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

---

## Scheduling Automatic Re-tests via the API

Register a schedule so Observatory retests your key URLs on its own cadence.
Use this alongside manual CI triggers to track drift between deployments.

```typescript
async function upsertSchedule(
  zoneId: string,
  token: string,
  pageUrl: string,
  frequency: "DAILY" | "WEEKLY",
  region = "us-central1",
): Promise<void> {
  const res = await fetch(
    `${CF_API}/zones/${zoneId}/speed_api/pages/${encodeURIComponent(pageUrl)}/schedule`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ region, frequency }),
    },
  );
  if (!res.ok) {
    throw new Error(`Schedule upsert failed: ${res.status} ${await res.text()}`);
  }
}
```

---

## Retrieving Historical Trends

```typescript
interface TrendEntry {
  timestamp: string;
  performanceScore: number;
}

async function fetchTrend(
  zoneId: string,
  token: string,
  pageUrl: string,
  region = "us-central1",
): Promise<TrendEntry[]> {
  const qs = new URLSearchParams({ region });
  const res = await fetch(
    `${CF_API}/zones/${zoneId}/speed_api/pages/${encodeURIComponent(pageUrl)}/trend?${qs}`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  const { result } = (await res.json()) as {
    result: { performanceScore: (number | null)[] };
  };
  // The API returns parallel arrays; timestamps are inferred from schedule cadence
  return result.performanceScore
    .map((score, i) => ({ timestamp: `run-${i}`, performanceScore: score ?? 0 }))
    .filter((e) => e.performanceScore > 0);
}
```

---

## CI/CD Integration Pattern (GitHub Actions)

```yaml
# .github/workflows/observatory.yml
name: Post-deploy Observatory Audit

on:
  workflow_run:
    workflows: ["Deploy to Production"]
    types: [completed]

jobs:
  audit:
    if: ${{ github.event.workflow_run.conclusion == 'success' }}
    runs-on: ubuntu-latest
    steps:
      - name: Trigger Observatory via Worker webhook
        run: |
          curl -sS -X POST \
            -H "Content-Type: application/json" \
            -d '{"url":"https://example.com/","region":"us-central1"}' \
            https://observatory-webhook.example.workers.dev
```

---

## Anti-patterns

- **Polling in a synchronous Worker request** — Observatory tests take 30-90 s;
  always defer polling to `ctx.waitUntil()` or a Queue consumer so the HTTP
  response returns immediately.
- **Testing every URL on every deploy** — Observatory has per-zone rate limits.
  Test only canonical pages (homepage, key landing pages) and use scheduled
  re-tests for the long tail.
- **Hardcoding the zone ID in source** — put it in a `wrangler.toml` variable,
  not in code checked into public repos.
- **Ignoring the `region` field** — default region may not reflect your primary
  audience.  Explicitly choose the region closest to your users.
- **Treating a score of 0 as valid** — a `0` in trend arrays means "no data",
  not a failing score.  Filter them before alerting.

---

## Gotchas

- The `url` path parameter must be **URL-encoded**.  Pass
  `encodeURIComponent("https://example.com/path")` — the raw URL with slashes
  and colons fails with a 404.
- Observatory can only test publicly reachable URLs.  Pages behind Cloudflare
  Access require a service-token bypass rule or must be tested in a staging
  zone.
- A zone can have at most one schedule per URL.  POSTing a second schedule
  overwrites the first silently.
- Lighthouse scores from the Observatory region differ from local DevTools
  because they use a real Chromium instance from a PoP with real network
  conditions.
- The `speed_api` endpoint family requires the **Zone.Speed** permission; the
  generic Zone:Read token used for most automation is insufficient.

---

## Verification

```bash
# Manually trigger a test and check the result
ZONE_ID="your-zone-id"
TOKEN="your-speed-api-token"
PAGE_URL="https://example.com/"

# Trigger
curl -sS -X POST \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/speed_api/pages/$(python3 -c "import urllib.parse; print(urllib.parse.quote('${PAGE_URL}', safe=''))")/tests" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"region":"us-central1"}' | jq .

# List tests for a page (shows status)
curl -sS \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/speed_api/pages/$(python3 -c "import urllib.parse; print(urllib.parse.quote('${PAGE_URL}', safe=''))")/tests" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.result[] | {id, status, .lighthouse.categories.performance.score}'
```

---

## Related

- `workers-logpush.md` — ship Observatory schedule run events to R2 for
  long-term trend storage
- `cloudflare-workers-cron-triggers-scheduling.md` — alternative to Observatory
  schedules: trigger tests via a Cron Worker for tighter control
- `workers-queues-patterns.md` — queue Observatory webhook payloads for
  reliable fan-out to multiple consumers (Slack, PagerDuty, dashboards)
- `wrangler-toml-reference.md` — externalizing zone ID and region config

---

## Sources

- Cloudflare Observatory REST API reference:
  https://developers.cloudflare.com/api/operations/speed-create-test
- Observatory overview:
  https://developers.cloudflare.com/speed/speed-test/
- Lighthouse scoring methodology:
  https://web.dev/articles/performance-scoring

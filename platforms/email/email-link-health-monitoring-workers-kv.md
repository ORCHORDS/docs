# Email Link Health Monitoring — Workers + KV

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A campaign goes out with a CTA pointing to a page that later returns 404, times out, or redirects to a competitor's domain after a domain acquisition. Recipients click, land on an error, and you have no alert. You need ongoing link health checks for all URLs embedded in sent campaigns, with Workers probing each URL and KV recording freshness state so your team is notified before the damage compounds.

## Context

Email links are frozen at send time. Unlike a website you can redeploy, every link in a sent message is permanent from the recipient's perspective. Link rot from product page restructuring, expiring coupon pages, and UTM-tagged landing pages taken offline is one of the top silent deliverability-adjacent problems — it increases complaint rates as recipients grow frustrated.

A Cloudflare Worker running on a cron trigger fetches the URL inventory from KV, probes each link with a `HEAD` request through Cloudflare's network, and writes status snapshots back to KV. A second Worker serves the current health map to your dashboard or webhook.

---

## 1. KV schema

```typescript
// Key: link:{campaignId}:{urlHash}
// Value: JSON
interface LinkRecord {
  url: string;
  campaignId: string;
  firstSeen: string;       // ISO 8601
  lastChecked: string | null;
  lastStatus: number | null;
  consecutiveFails: number;
  alertSent: boolean;
}

// Index key: campaign:{campaignId}:links → JSON array of urlHashes
```

Register links at send time:

```typescript
async function registerLink(
  kv: KVNamespace,
  campaignId: string,
  url: string
): Promise<void> {
  const hash = await urlHash(url); // SHA-256 hex, first 12 chars
  const key = `link:${campaignId}:${hash}`;
  const existing = await kv.get(key);
  if (existing) return; // idempotent

  const record: LinkRecord = {
    url,
    campaignId,
    firstSeen: new Date().toISOString(),
    lastChecked: null,
    lastStatus: null,
    consecutiveFails: 0,
    alertSent: false,
  };
  await kv.put(key, JSON.stringify(record), { expirationTtl: 90 * 86400 }); // 90 days

  // Append to campaign index
  const idxKey = `campaign:${campaignId}:links`;
  const idx: string[] = JSON.parse((await kv.get(idxKey)) ?? "[]");
  if (!idx.includes(hash)) {
    idx.push(hash);
    await kv.put(idxKey, JSON.stringify(idx));
  }
}

async function urlHash(url: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(url));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, "0")).join("").slice(0, 12);
}
```

## 2. Probe links on a cron trigger

```typescript
// wrangler.toml
// [triggers]
// crons = ["0 * * * *"]   # hourly

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    // List all link keys (paginate if large)
    const list = await env.LINK_KV.list({ prefix: "link:" });

    const probes = list.keys.map(({ name }) =>
      ctx.waitUntil(probeLink(env, name))
    );
    await Promise.allSettled(probes);
  },
};

async function probeLink(env: Env, kvKey: string): Promise<void> {
  const raw = await env.LINK_KV.get(kvKey);
  if (!raw) return;
  const record: LinkRecord = JSON.parse(raw);

  let status: number;
  try {
    const res = await fetch(record.url, {
      method: "HEAD",
      redirect: "follow",
      signal: AbortSignal.timeout(8000),
      headers: { "User-Agent": "EmailLinkMonitor/1.0" },
    });
    status = res.status;
  } catch {
    status = 0; // network error / timeout
  }

  const healthy = status >= 200 && status < 400;
  record.lastChecked = new Date().toISOString();
  record.lastStatus = status;
  record.consecutiveFails = healthy ? 0 : record.consecutiveFails + 1;

  if (!healthy && record.consecutiveFails >= 3 && !record.alertSent) {
    await sendAlert(env, record);
    record.alertSent = true;
  }
  if (healthy) record.alertSent = false; // reset on recovery

  await env.LINK_KV.put(kvKey, JSON.stringify(record));
}
```

## 3. Send alerts via email or webhook

```typescript
async function sendAlert(env: Env, record: LinkRecord): Promise<void> {
  const body = JSON.stringify({
    text: `Link health alert: ${record.url} returned ${record.lastStatus ?? "timeout"} (campaign ${record.campaignId})`,
    url: record.url,
    campaignId: record.campaignId,
    consecutiveFails: record.consecutiveFails,
  });

  await fetch(env.ALERT_WEBHOOK_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
```

## 4. Health summary API endpoint

```typescript
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const campaignId = url.searchParams.get("campaignId");
    if (!campaignId) return new Response("Missing campaignId", { status: 400 });

    const idxKey = `campaign:${campaignId}:links`;
    const hashes: string[] = JSON.parse((await env.LINK_KV.get(idxKey)) ?? "[]");

    const records = await Promise.all(
      hashes.map(async (h) => {
        const raw = await env.LINK_KV.get(`link:${campaignId}:${h}`);
        return raw ? (JSON.parse(raw) as LinkRecord) : null;
      })
    );

    const healthy = records.filter((r) => r && r.lastStatus && r.lastStatus < 400).length;
    const broken = records.filter((r) => r && (!r.lastStatus || r.lastStatus >= 400)).length;

    return new Response(
      JSON.stringify({ campaignId, total: records.length, healthy, broken, links: records }),
      { headers: { "Content-Type": "application/json" } }
    );
  },
};
```

## 5. Handling redirect chains

A 301 to a parked domain is a common failure mode. Follow redirects but record the final URL:

```typescript
async function probeWithFinalUrl(url: string): Promise<{ status: number; finalUrl: string }> {
  const res = await fetch(url, { method: "HEAD", redirect: "follow", signal: AbortSignal.timeout(8000) });
  return { status: res.status, finalUrl: res.url };
}
// Flag if finalUrl !== original URL (unexpected redirect target)
```

---

## Anti-patterns

- **Probing every link on every Worker invocation without pagination** — KV `list()` returns at most 1000 keys per call; paginate using the `cursor` field for large inventories.
- **Probing with GET instead of HEAD** — downloads entire response bodies for no reason; HEAD is sufficient for status code verification and far cheaper.
- **Alerting on the first failure** — transient network blips trigger false positives; wait for `consecutiveFails >= 3` (3 hours on an hourly cron).
- **Keeping link records forever** — set `expirationTtl` at registration; 90 days after a campaign ends, old link records have no operational value.

## Gotchas

- Some servers return 405 (Method Not Allowed) for HEAD. Retry with GET on 405 to get a usable status.
- KV `list()` does not return values, only keys and metadata. Each probe still requires a `get()` call — batch wisely to stay within KV rate limits (1000 reads/s on free, unlimited on paid).
- `fetch()` in Workers follows redirects by default; a link that permanently redirects to `https://parked.example.com` will return 200, masking the problem. Always compare `res.url` to the original.
- `AbortSignal.timeout()` is available in Workers runtime; do not use `setTimeout` + manual abort.

## Verification

1. Manually set a test KV record pointing to `https://httpstat.us/404` and confirm an alert fires within 3 cron cycles.
2. Confirm `consecutiveFails` resets to 0 when the URL recovers (point test record at a healthy URL).
3. Check KV key count with `wrangler kv key list --prefix "link:"` to confirm TTL expiry is working.

## Related

- `email-click-tracking.md`
- `email-link-rewriting-utm-workers.md`
- `email-preview-link-tracking-kv-workers.md`
- `email-campaign-cost-estimation-d1-workers.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/workers/runtime-apis/fetch/

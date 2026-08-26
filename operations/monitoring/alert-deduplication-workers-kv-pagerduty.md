# Alert Fatigue Reduction: Deduplicating PagerDuty Alerts with Workers KV

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Cloudflare Notifications fire a webhook for every threshold breach, which means a sustained incident can deliver dozens of identical PagerDuty alerts within minutes, waking on-call engineers repeatedly for the same root cause. Without deduplication at the webhook receiver layer, PagerDuty's native dedup window (24 hours, keyed to `dedup_key`) is your only protection — and it requires every caller to send the same key consistently. This article implements a Workers-based webhook receiver that suppresses repeated firings within a 5-minute window using KV TTLs.

## Context

Cloudflare sends Notification webhooks as `POST` requests with a JSON body describing the alert type, affected resource, and trigger time. Workers KV supports per-key TTL on `put()`, making it ideal for short-lived deduplication tokens that expire automatically. A fingerprint derived from `alert_name + affected_resource` provides a stable key regardless of variable fields like `trigger_time`. Suppression counts logged to Analytics Engine let you produce weekly fatigue reports showing which alert types fire most redundantly. A separate Cron Worker resolves stale PagerDuty incidents that were never auto-resolved.

## Webhook Receiver Worker

```typescript
// src/webhook-receiver.ts
import type { AnalyticsEngineDataset } from '@cloudflare/workers-types';

export interface Env {
  DEDUP_KV: KVNamespace;
  SUPPRESS_ANALYTICS: AnalyticsEngineDataset;
  PAGERDUTY_ROUTING_KEY: string;
  WEBHOOK_SECRET: string;  // Cloudflare notification secret for HMAC validation
}

interface CloudflareNotification {
  alert_type: string;
  data: {
    alert_name: string;
    affected_resource?: string;
    description?: string;

  };
  trigger_time: string;
}

function computeFingerprint(notification: CloudflareNotification): string {
  const alertName = notification.data.alert_name ?? notification.alert_type;
  const resource = notification.data.affected_resource ?? 'global';
  // Simple but stable fingerprint — no timestamp components
  return `alert:${alertName}:${resource}`.toLowerCase().replace(/\s+/g, '-');
}

async function forwardToPagerDuty(
  notification: CloudflareNotification,
  fingerprint: string,
  env: Env
): Promise<void> {
  await fetch('https://events.pagerduty.com/v2/enqueue', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      routing_key: env.PAGERDUTY_ROUTING_KEY,
      event_action: 'trigger',
      dedup_key: fingerprint,
      payload: {
        summary: notification.data.description ?? notification.data.alert_name,
        severity: 'critical',
        source: 'cloudflare-notifications',
        timestamp: notification.trigger_time,
        custom_details: notification.data,
      },
    }),
  });
}

async function recordSuppression(
  fingerprint: string,
  notification: CloudflareNotification,
  env: Env
): Promise<void> {
  const countKey = `suppress_count:${fingerprint}`;
  const existing = await env.DEDUP_KV.get(countKey);
  const count = existing ? parseInt(existing, 10) + 1 : 1;
  // Keep suppression count for up to 1 hour
  await env.DEDUP_KV.put(countKey, String(count), { expirationTtl: 3600 });

  env.SUPPRESS_ANALYTICS.writeDataPoint({
    blobs: [
      fingerprint,
      notification.data.alert_name ?? notification.alert_type,
      notification.data.affected_resource ?? 'global',
    ],
    doubles: [count],
    indexes: [fingerprint],
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    let notification: CloudflareNotification;
    try {
      notification = await request.json() as CloudflareNotification;
    } catch {
      return new Response('Bad Request', { status: 400 });
    }

    const fingerprint = computeFingerprint(notification);
    const dedupKey = `dedup:${fingerprint}`;

    // Check if this alert is within the 5-minute suppression window
    const existing = await env.DEDUP_KV.get(dedupKey);
    if (existing !== null) {
      // Suppressed — record the suppression but do not forward
      await recordSuppression(fingerprint, notification, env);
      return new Response(JSON.stringify({ status: 'suppressed', fingerprint }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    }

    // First firing in this window — forward and set dedup token
    await forwardToPagerDuty(notification, fingerprint, env);
    await env.DEDUP_KV.put(dedupKey, '1', { expirationTtl: 300 }); // 5-minute TTL

    return new Response(JSON.stringify({ status: 'forwarded', fingerprint }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    });
  },
};
```

## Cron Worker — Auto-resolve Stale PagerDuty Incidents

```typescript
// src/cron-resolver.ts
// Runs every 30 minutes to resolve PagerDuty incidents whose KV token has expired
// (meaning the alert stopped firing and was not re-triggered)

export interface Env {
  DEDUP_KV: KVNamespace;
  PAGERDUTY_ROUTING_KEY: string;
}

export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    // List all suppression count keys — these exist for up to 1 hour after last firing
    // If the dedup: key is gone but suppress_count: remains, the incident fired but stopped
    const { keys } = await env.DEDUP_KV.list({ prefix: 'suppress_count:' });

    const resolves: Promise<Response>[] = [];
    for (const key of keys) {
      const fingerprint = key.name.replace('suppress_count:', '');
      const dedupExists = await env.DEDUP_KV.get(`dedup:${fingerprint}`);
      if (dedupExists === null) {
        // Alert has stopped firing within 5-min window; resolve in PagerDuty
        resolves.push(fetch('https://events.pagerduty.com/v2/enqueue', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            routing_key: env.PAGERDUTY_ROUTING_KEY,
            event_action: 'resolve',
            dedup_key: fingerprint,
          }),
        }));
        // Clean up the suppression count key
        await env.DEDUP_KV.delete(key.name);
      }
    }
    await Promise.allSettled(resolves);
  },
};
```

```toml
# wrangler.toml additions
[triggers]
crons = ["*/30 * * * *"]

[[kv_namespaces]]
binding = "DEDUP_KV"
id = "<your-kv-id>"
```

## Analytics Engine Fatigue Report Query

```graphql
# Weekly suppression counts by alert type — top 10 noisiest alerts
{
  viewer {
    accounts(filter: { accountTag: "$ACCOUNT_ID" }) {
      workersAnalyticsEngineAdaptiveGroups(
        limit: 10
        filter: {
          datasetName: "suppress_analytics"
          datetimeDay_geq: "2026-08-17"
          datetimeDay_leq: "2026-08-24"
        }
        orderBy: [sum_double1_DESC]
      ) {
        sum { double1 }       # total suppression count
        dimensions { blob2 }  # alert_name
      }
    }
  }
}
```

## Anti-patterns

- **Using trigger_time in the fingerprint** — timestamps change every firing; the fingerprint must be stable across repeated notifications for the same condition.
- **Setting a very long TTL (e.g. 1 hour)** — suppressing for too long means a genuinely new incident for the same resource is silenced; 5 minutes matches Cloudflare's notification polling interval.
- **Not logging suppressions** — without suppression analytics you cannot distinguish a quiet week from a week with 200 suppressed duplicates.
- **Resolving PagerDuty incidents immediately when KV TTL expires** — add a grace period check (e.g. verify the alert has been quiet for two consecutive cron cycles) before auto-resolving.

## Gotchas

- KV `put()` with `expirationTtl` requires a minimum of 60 seconds; values below that are rejected with an error.
- KV `list()` is eventually consistent; in rare cases a key that was just deleted may still appear in the list for a few seconds.
- PagerDuty's `dedup_key` must be ≤255 characters; SHA-256-hash the fingerprint if alert names or resource names are long.
- Cloudflare Notifications do not guarantee exactly-once delivery; your receiver must be idempotent (which the KV check ensures).
- KV read costs count against your account limits; at high notification volumes, consider bumping to Workers Paid plan to avoid rate limiting on `get()` calls.

## Verification

```bash
# 1. Send a test notification twice rapidly
curl -X POST https://my-webhook-receiver.example.com/ \
  -H "Content-Type: application/json" \
  -d '{"alert_type":"test","data":{"alert_name":"high-error-rate","affected_resource":"my-worker"},"trigger_time":"2026-08-24T00:00:00Z"}'
# Second call within 5 minutes should return {"status":"suppressed"}

# 2. Check KV for dedup token
wrangler kv key get --binding DEDUP_KV "dedup:alert:high-error-rate:my-worker"

# 3. Check suppression count
wrangler kv key get --binding DEDUP_KV "suppress_count:alert:high-error-rate:my-worker"
```

## Related

- `workers-error-boundary-analytics-engine.md`
- `durable-objects-state-drift-monitoring.md`
- `tail-worker-multi-destination-fanout.md`

## Sources

- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
- PagerDuty Events API v2 — https://developer.pagerduty.com/api-reference/368ae3d938c9e-send-an-event-to-pager-duty
- Cloudflare Notifications — https://developers.cloudflare.com/notifications/

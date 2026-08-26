# Google Postmaster Tools API Polling with Workers and Analytics Engine

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Google Postmaster Tools surfaces domain reputation, spam rate, and delivery error data, but its web UI offers no programmatic export and no alerting. You want a Cloudflare Worker on a daily Cron Trigger to fetch domain-level reputation metrics from the Postmaster Tools API, write them to Analytics Engine for long-term trend queries, and emit a webhook alert when spam rate or reputation degrades below threshold.

## Context

The Gmail Postmaster Tools API (`gmailpostmastertools.googleapis.com`) requires a Google service-account JWT to obtain OAuth 2 access tokens. Workers cannot import Node-only Google SDK packages, so the OAuth handshake is done manually via `fetch` to `oauth2.googleapis.com`. Metrics are stored as `writeDataPoint` calls to an Analytics Engine dataset, enabling GraphQL queries over rolling 30-day windows. A KV namespace caches the access token between Cron firings to avoid unnecessary token refreshes.

## Service Account JWT and Token Exchange

```typescript
// src/auth.ts
export interface Env {
  POSTMASTER_KV: KVNamespace;
  GOOGLE_SA_KEY: string; // JSON service-account key stored as Worker secret
}

interface ServiceAccountKey {
  client_email: string;
  private_key: string;
}

async function signJwt(header: object, payload: object, pemKey: string): Promise<string> {
  const enc = (v: object) =>
    btoa(JSON.stringify(v)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const message = `${enc(header)}.${enc(payload)}`;

  const keyData = pemKey
    .replace(/-----[^-]+-----/g, '')
    .replace(/\s/g, '');
  const keyBytes = Uint8Array.from(atob(keyData), (c) => c.charCodeAt(0));
  const key = await crypto.subtle.importKey(
    'pkcs8', keyBytes,
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false, ['sign']
  );
  const sig = await crypto.subtle.sign(
    'RSASSA-PKCS1-v1_5', key,
    new TextEncoder().encode(message)
  );
  const sigB64 = btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  return `${message}.${sigB64}`;
}

export async function getAccessToken(env: Env): Promise<string> {
  const cached = await env.POSTMASTER_KV.get('google_access_token');
  if (cached) return cached;

  const sa: ServiceAccountKey = JSON.parse(env.GOOGLE_SA_KEY);
  const now = Math.floor(Date.now() / 1000);
  const jwt = await signJwt(
    { alg: 'RS256', typ: 'JWT' },
    {
      iss: sa.client_email,
      scope: 'https://www.googleapis.com/auth/postmaster.readonly',
      aud: 'https://oauth2.googleapis.com/token',
      iat: now, exp: now + 3600,
    },
    sa.private_key
  );

  const res = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: `grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion=${jwt}`,
  });
  const { access_token, expires_in } = await res.json<{
    access_token: string; expires_in: number;
  }>();

  await env.POSTMASTER_KV.put('google_access_token', access_token, {
    expirationTtl: expires_in - 60,
  });
  return access_token;
}
```

## Fetching Metrics and Writing to Analytics Engine

```typescript
// src/metrics.ts
interface DomainReputationMetrics {
  domainReputation: string;          // HIGH | MEDIUM | LOW | BAD
  spamRatio: number | null;
  inboxPlacementRate: number | null;
}

export async function fetchDomainTrafficStats(
  domain: string,
  token: string,
  date: string // YYYY-MM-DD
): Promise<DomainReputationMetrics | null> {
  const encodedDomain = encodeURIComponent(`domains/${domain}`);
  const res = await fetch(
    `https://gmailpostmastertools.googleapis.com/v1/${encodedDomain}/trafficStats/${date.replace(/-/g, '')}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  if (res.status === 404) return null; // no data for this date
  if (!res.ok) throw new Error(`Postmaster API error: ${res.status}`);
  const data = await res.json<{
    domainReputation?: string;
    spamRatio?: number;
    inboxPlacementRate?: number;
  }>();
  return {
    domainReputation: data.domainReputation ?? 'UNKNOWN',
    spamRatio: data.spamRatio ?? null,
    inboxPlacementRate: data.inboxPlacementRate ?? null,
  };
}

export interface AnalyticsEnv {
  EMAIL_METRICS: AnalyticsEngineDataset;
  ALERT_WEBHOOK_URL: string;
}

const REPUTATION_RANK: Record<string, number> = {
  HIGH: 4, MEDIUM: 3, LOW: 2, BAD: 1, UNKNOWN: 0,
};

export async function ingestMetrics(
  env: AnalyticsEnv,
  domain: string,
  date: string,
  metrics: DomainReputationMetrics
): Promise<void> {
  env.EMAIL_METRICS.writeDataPoint({
    blobs: [domain, date, metrics.domainReputation],
    doubles: [
      REPUTATION_RANK[metrics.domainReputation] ?? 0,
      metrics.spamRatio ?? -1,
      metrics.inboxPlacementRate ?? -1,
    ],
    indexes: [domain],
  });

  // Alert if reputation degrades below MEDIUM or spam ratio exceeds 0.1 %
  if (
    REPUTATION_RANK[metrics.domainReputation] <= 2 ||
    (metrics.spamRatio !== null && metrics.spamRatio > 0.001)
  ) {
    await fetch(env.ALERT_WEBHOOK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ domain, date, metrics, alert: 'REPUTATION_DEGRADED' }),
    });
  }
}
```

## Scheduled Handler Wiring

```typescript
// src/worker.ts
import { getAccessToken } from './auth';
import { fetchDomainTrafficStats, ingestMetrics } from './metrics';

interface Env extends AnalyticsEnv {
  POSTMASTER_KV: KVNamespace;
  GOOGLE_SA_KEY: string;
  MONITORED_DOMAINS: string; // comma-separated, e.g. "example.com,mail.example.com"
  ALERT_WEBHOOK_URL: string;
  EMAIL_METRICS: AnalyticsEngineDataset;
}

export const scheduled: ExportedHandlerScheduledHandler<Env> = async (_event, env) => {
  const token = await getAccessToken(env);
  const yesterday = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
  const domains = env.MONITORED_DOMAINS.split(',').map((d) => d.trim());

  for (const domain of domains) {
    const metrics = await fetchDomainTrafficStats(domain, token, yesterday);
    if (!metrics) {
      console.warn(`No Postmaster data for ${domain} on ${yesterday}`);
      continue;
    }
    await ingestMetrics(env, domain, yesterday, metrics);
    console.log(`Ingested metrics for ${domain}: reputation=${metrics.domainReputation}`);
  }
};

export default { scheduled } satisfies ExportedHandler<Env>;
```

## Anti-patterns

- Storing the service-account private key in `wrangler.toml` — always use a Worker secret set via `wrangler secret put GOOGLE_SA_KEY`.
- Calling the token endpoint on every Cron firing instead of caching in KV — Google rate-limits token issuance per service account.
- Writing one Analytics Engine row per metric field instead of combining doubles into a single `writeDataPoint` call — batching saves write quota.

## Gotchas

- The Postmaster API returns an empty 200 (or 404) for dates with insufficient traffic volume; treat `null` metrics as normal, not an error.
- `domainReputation` uses string literals (`HIGH`, `MEDIUM`, `LOW`, `BAD`) — map them to integers before storing in Analytics Engine doubles.

## Verification

```bash
# Trigger manually via Cron test endpoint
wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=0+6+*+*+*"

# Query Analytics Engine for last 7 days
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT blob1 AS domain, blob2 AS date, double1 AS reputationScore FROM EMAIL_METRICS ORDER BY date DESC LIMIT 50"}'
```

## Related

- `email/google-postmaster-setup.md`
- `email/email-reputation-monitoring.md`
- `email/email-deliverability-monitoring-workers-logpush.md`
- `email/complaint-rate-monitoring.md`

## Sources

- https://developers.google.com/workspace/gmail/postmaster/reference/rest
- https://developers.cloudflare.com/analytics/analytics-engine/worker-binding/
- https://developers.cloudflare.com/workers/runtime-apis/scheduled-event/

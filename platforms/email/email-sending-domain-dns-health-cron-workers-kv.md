# Email Sending Domain DNS Health Monitoring — Workers Cron + KV

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

SPF, DKIM, DMARC, or MX records drift silently after a DNS migration or ESP
change. Deliverability collapses hours later, and the alert is a spike in
bounces, not a proactive notification. You need a cron-driven Worker that
checks all DNS records for every sending domain on a schedule and pages you
before mail queues start rejecting.

---

## Context

Cloudflare Workers Cron Triggers can fire on any cron schedule and have full
outbound DNS resolution via `fetch` against public DNS-over-HTTPS (DoH) APIs.
KV stores the last-known-good state per domain and record type. When a record
changes or disappears, the Worker writes an alert to an alerting endpoint (PagerDuty,
Slack, email) and updates KV with the incident timestamp so it does not spam
repeat pages.

---

## KV Key Layout

```
dns-health:{domain}:spf          → { value: "v=spf1 ...", lastOk: 1234567890 }
dns-health:{domain}:dkim:{selector} → { value: "v=DKIM1 ...", lastOk: ... }
dns-health:{domain}:dmarc        → { value: "v=DMARC1 ...", lastOk: ... }
dns-health:{domain}:mx           → { value: ["mx1.example.com","mx2.example.com"], lastOk: ... }
dns-health:{domain}:incident     → { since: 1234567890, lastAlerted: ... }
```

---

## DNS-over-HTTPS Helper

```typescript
// src/dns-check.ts
const DOH_ENDPOINT = 'https://cloudflare-dns.com/dns-query';

export async function resolveTxt(name: string): Promise<string[]> {
  const url = `${DOH_ENDPOINT}?name=${encodeURIComponent(name)}&type=TXT`;
  const res = await fetch(url, { headers: { Accept: 'application/dns-json' } });
  if (!res.ok) throw new Error(`DoH TXT lookup failed for ${name}: ${res.status}`);
  const data = await res.json<{ Answer?: { data: string }[] }>();
  return (data.Answer ?? []).map((a) => a.data.replace(/"/g, ''));
}

export async function resolveMx(domain: string): Promise<string[]> {
  const url = `${DOH_ENDPOINT}?name=${encodeURIComponent(domain)}&type=MX`;
  const res = await fetch(url, { headers: { Accept: 'application/dns-json' } });
  const data = await res.json<{ Answer?: { data: string }[] }>();
  return (data.Answer ?? []).map((a) => a.data.split(' ')[1]?.replace(/\.$/, '') ?? '');
}
```

---

## Cron Worker — Check All Domains

```typescript
// src/workers/dns-health-cron.ts
export interface Env {
  DNS_STATE: KVNamespace;
  ALERT_WEBHOOK: string;   // Slack or PagerDuty incoming webhook URL
  DOMAINS_JSON: string;    // JSON array: [{ domain, dkimSelectors: string[] }]
}

interface DomainConfig { domain: string; dkimSelectors: string[] }

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const domains: DomainConfig[] = JSON.parse(env.DOMAINS_JSON);

    for (const cfg of domains) {
      await checkDomain(cfg, env);
    }
  }
};

async function checkDomain(cfg: DomainConfig, env: Env): Promise<void> {
  const { domain, dkimSelectors } = cfg;
  const errors: string[] = [];

  // --- SPF ---
  const spfRecords = await resolveTxt(domain);
  const spf = spfRecords.find((r) => r.startsWith('v=spf1'));
  await checkRecord(env, `${domain}:spf`, spf ?? null, errors, `SPF missing on ${domain}`);

  // --- DMARC ---
  const dmarcRecords = await resolveTxt(`_dmarc.${domain}`);
  const dmarc = dmarcRecords.find((r) => r.startsWith('v=DMARC1'));
  await checkRecord(env, `${domain}:dmarc`, dmarc ?? null, errors, `DMARC missing on ${domain}`);

  // --- DKIM per selector ---
  for (const sel of dkimSelectors) {
    const dkimRecords = await resolveTxt(`${sel}._domainkey.${domain}`);
    const dkim = dkimRecords.find((r) => r.startsWith('v=DKIM1'));
    await checkRecord(env, `${domain}:dkim:${sel}`, dkim ?? null, errors,
      `DKIM selector ${sel} missing on ${domain}`);
  }

  // --- MX ---
  const mx = await resolveMx(domain);
  const mxValue = mx.sort().join(',');
  await checkRecord(env, `${domain}:mx`, mxValue || null, errors,
    `MX records missing on ${domain}`);

  if (errors.length > 0) {
    await fireAlert(env, domain, errors);
  } else {
    // Clear any open incident
    await env.DNS_STATE.delete(`dns-health:${domain}:incident`);
  }
}
```

---

## Record Comparison and State Management

```typescript
// src/workers/dns-health-cron.ts (continued)
async function checkRecord(
  env: Env,
  key: string,
  current: string | null,
  errors: string[],
  errorMsg: string
): Promise<void> {
  const stateKey = `dns-health:${key}`;
  const stored = await env.DNS_STATE.get(stateKey, 'json') as
    { value: string; lastOk: number } | null;

  if (!current) {
    errors.push(errorMsg);
    return;
  }

  if (stored && stored.value !== current) {
    errors.push(`${key} changed: was "${stored.value.slice(0, 60)}…" now "${current.slice(0, 60)}…"`);
  }

  // Always update to latest good value
  await env.DNS_STATE.put(stateKey, JSON.stringify({
    value: current,
    lastOk: Math.floor(Date.now() / 1000)
  }));
}

async function fireAlert(env: Env, domain: string, errors: string[]): Promise<void> {
  const incidentKey = `dns-health:${domain}:incident`;
  const existing = await env.DNS_STATE.get(incidentKey, 'json') as
    { since: number; lastAlerted: number } | null;
  const now = Math.floor(Date.now() / 1000);

  // Suppress repeat pages within 4 hours
  if (existing && now - existing.lastAlerted < 4 * 3600) return;

  await fetch(env.ALERT_WEBHOOK, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: `*DNS Health Alert — ${domain}*\n` + errors.map((e) => `• ${e}`).join('\n'),
    }),
  });

  await env.DNS_STATE.put(incidentKey, JSON.stringify({
    since: existing?.since ?? now,
    lastAlerted: now,
  }));
}
```

---

## wrangler.toml Cron Configuration

```toml
[[triggers.crons]]
crons = ["*/15 * * * *"]   # every 15 minutes

[vars]
DOMAINS_JSON = '[{"domain":"mail.example.com","dkimSelectors":["s1","s2"]}]'
```

---

## Anti-patterns

- **Querying authoritative nameservers directly** — rate-limit errors and TTL
  variance make results noisy. Cloudflare DoH is cached, fast, and globally
  anycast — use it.
- **Alerting on every cron tick while degraded** — without the 4-hour
  suppression window you flood on-call with duplicate pages.
- **Storing the entire TXT record string without trimming** — DKIM public-key
  records can exceed 450 chars; truncate for the log message but store in full
  for comparison.

---

## Gotchas

- Some ESP DKIM selectors have TTLs of 300 s; the first check after a rotation
  may read the old key from a resolver cache. Wait one full TTL before treating
  a mismatch as an incident.
- `application/dns-json` (DoH JSON) is a Cloudflare extension; other DoH
  providers (e.g., Google `8.8.8.8/resolve`) also support it but with minor
  response-shape differences.
- KV reads inside a high-frequency cron can accumulate meaningful read costs
  at scale; batch domain lookups with `getWithMetadata` if your plan is
  sensitive to KV read operations.

---

## Verification

```bash
# Run the cron locally
wrangler dev --test-scheduled
# In another terminal:
curl "http://localhost:8787/__scheduled?cron=*/15+*+*+*+*"

# Inspect stored state
wrangler kv key get --binding DNS_STATE "dns-health:mail.example.com:spf"

# Simulate a missing record by checking with dig
dig +short TXT _dmarc.mail.example.com
```

---

## Related

- `email-dkim-rotation-workers-kv.md`
- `email-spf-flattening-workers.md`
- `email-deliverability-monitoring-workers-logpush.md`

---

## Sources

- Cloudflare DNS-over-HTTPS JSON — https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/make-api-requests/json/
- Cloudflare Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Cloudflare KV — https://developers.cloudflare.com/kv/

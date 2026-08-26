# Email IP & Domain Blacklist Delisting Automation with Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A sending IP or domain appears on a DNSBL (DNS-Based Blackhole List) or the Google/
Yahoo Postmaster spam rate exceeds 0.3%, causing deliverability to drop sharply.
The ops team discovers the listing hours later, after support tickets pile up about
undelivered emails. The example project platform needs a Workers cron job that continuously
monitors known blacklists, writes incidents to D1, sends an alert email, and — for
DNSBLs that offer automated delisting — submits the delisting request without human
intervention.

---

## Context

DNSBLs expose listing status via DNS: query `{reversed_ip}.{dnsbl_zone}`. If the
response is an A record (typically `127.0.0.x`), the IP is listed. The return code
encodes the reason (spamtrap hit, abuse report, etc.). Cloudflare Workers can perform
DNS lookups via `fetch` against the Cloudflare DNS-over-HTTPS (DoH) endpoint, since
raw DNS socket access is not available in the runtime.

Major lists to monitor:
- Spamhaus ZEN (`zen.spamhaus.org`)
- Spamhaus DBL (`dbl.spamhaus.org`) — domain-based
- Barracuda BRBL (`b.barracudacentral.org`)
- SURBL (`multi.surbl.org`) — domain-based
- Sorbs DNSBL (`dnsbl.sorbs.net`)
- SpamCop BL (`bl.spamcop.net`)

---

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS blacklist_checks (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  checked_at    TEXT NOT NULL,   -- ISO-8601
  target        TEXT NOT NULL,   -- IP or domain
  target_type   TEXT NOT NULL,   -- 'ip' or 'domain'
  dnsbl         TEXT NOT NULL,
  listed        INTEGER NOT NULL DEFAULT 0,
  return_code   TEXT,            -- e.g. "127.0.0.2"
  reason        TEXT
);
CREATE INDEX IF NOT EXISTS idx_bl_target ON blacklist_checks (target, dnsbl, checked_at);

CREATE TABLE IF NOT EXISTS delisting_requests (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  requested_at  TEXT NOT NULL,
  target        TEXT NOT NULL,
  dnsbl         TEXT NOT NULL,
  method        TEXT NOT NULL,   -- 'api', 'form', 'manual'
  status        TEXT NOT NULL DEFAULT 'pending',
  response_body TEXT
);
```

---

## DNS-over-HTTPS Lookup via Cloudflare DoH

```typescript
// src/blacklist/dns.ts

const DOH_ENDPOINT = 'https://cloudflare-dns.com/dns-query';

export async function lookupA(fqdn: string): Promise<string[]> {
  const url = new URL(DOH_ENDPOINT);
  url.searchParams.set('name', fqdn);
  url.searchParams.set('type', 'A');

  const res = await fetch(url.toString(), {
    headers: { accept: 'application/dns-json' },
  });

  if (!res.ok) throw new Error(`DoH error: ${res.status}`);

  const data = await res.json<{
    Answer?: { type: number; data: string }[];
  }>();

  return (data.Answer ?? [])
    .filter((r) => r.type === 1)  // type 1 = A record
    .map((r) => r.data);
}

export function reverseIp(ip: string): string {
  return ip.split('.').reverse().join('.');
}

/** Returns the return code string if listed, null if clean. */
export async function checkIpOnDnsbl(
  ip: string,
  dnsbl: string,
): Promise<string | null> {
  const query = `${reverseIp(ip)}.${dnsbl}`;
  try {
    const results = await lookupA(query);
    return results.length > 0 ? results[0] : null;
  } catch {
    return null;  // NXDOMAIN = not listed
  }
}

export async function checkDomainOnDnsbl(
  domain: string,
  dnsbl: string,
): Promise<string | null> {
  const query = `${domain}.${dnsbl}`;
  try {
    const results = await lookupA(query);
    return results.length > 0 ? results[0] : null;
  } catch {
    return null;
  }
}
```

---

## Blacklist Reason Decoder

```typescript
// src/blacklist/reasons.ts

const SPAMHAUS_ZEN_CODES: Record<string, string> = {
  '127.0.0.2': 'SBL — Spamhaus Block List (spam source)',
  '127.0.0.3': 'SBL CSS — Snowshoe spam',
  '127.0.0.4': 'XBL — CBL (Composite Blocking List) exploited',
  '127.0.0.9': 'SBL DROP — Do Not Route',
  '127.0.0.10': 'PBL — Policy Block List (dynamic IP)',
  '127.0.0.11': 'PBL — ISP Maintained',
};

const RETURN_CODE_MAPS: Record<string, Record<string, string>> = {
  'zen.spamhaus.org': SPAMHAUS_ZEN_CODES,
  'dnsbl.sorbs.net': {
    '127.0.0.2': 'HTTP proxy',
    '127.0.0.3': 'SOCKS proxy',
    '127.0.0.5': 'Spam source',
    '127.0.0.8': 'Dynamic IP',
  },
};

export function decodeReason(dnsbl: string, returnCode: string): string {
  const map = RETURN_CODE_MAPS[dnsbl];
  if (!map) return `Listed (code: ${returnCode})`;
  return map[returnCode] ?? `Unknown code: ${returnCode}`;
}
```

---

## Cron Worker: Monitor and Record

```typescript
// src/index.ts
import type { ScheduledEvent } from '@cloudflare/workers-types';
import { checkIpOnDnsbl, checkDomainOnDnsbl } from './blacklist/dns';
import { decodeReason }                         from './blacklist/reasons';
import { sendAlert }                            from './blacklist/alert';
import { requestDelisting }                     from './blacklist/delisting';

export interface Env {
  DB: D1Database;
  ALERT_TO: string;
  SENDING_IPS: string;   // comma-separated
  SENDING_DOMAINS: string;
}

const IP_DNSBLS    = ['zen.spamhaus.org', 'b.barracudacentral.org', 'bl.spamcop.net', 'dnsbl.sorbs.net'];
const DOMAIN_DNSBLS = ['dbl.spamhaus.org', 'multi.surbl.org'];

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const ips     = env.SENDING_IPS.split(',').map((s) => s.trim());
    const domains = env.SENDING_DOMAINS.split(',').map((s) => s.trim());
    const now     = new Date().toISOString();
    const newListings: { target: string; dnsbl: string; reason: string }[] = [];

    // Check IPs
    for (const ip of ips) {
      for (const dnsbl of IP_DNSBLS) {
        const code = await checkIpOnDnsbl(ip, dnsbl);
        const listed = code !== null;
        const reason = listed ? decodeReason(dnsbl, code!) : null;

        await env.DB.prepare(
          `INSERT INTO blacklist_checks (checked_at, target, target_type, dnsbl, listed, return_code, reason)
           VALUES (?, ?, 'ip', ?, ?, ?, ?)`,
        ).bind(now, ip, dnsbl, listed ? 1 : 0, code, reason).run();

        if (listed) newListings.push({ target: ip, dnsbl, reason: reason! });
      }
    }

    // Check domains
    for (const domain of domains) {
      for (const dnsbl of DOMAIN_DNSBLS) {
        const code = await checkDomainOnDnsbl(domain, dnsbl);
        const listed = code !== null;

        await env.DB.prepare(
          `INSERT INTO blacklist_checks (checked_at, target, target_type, dnsbl, listed, return_code, reason)
           VALUES (?, ?, 'domain', ?, ?, ?, ?)`,
        ).bind(now, domain, dnsbl, listed ? 1 : 0, code, listed ? `Listed: ${code}` : null).run();

        if (listed) newListings.push({ target: domain, dnsbl, reason: `Listed (${code})` });
      }
    }

    // Alert and attempt auto-delisting for new listings
    if (newListings.length > 0) {
      ctx.waitUntil(sendAlert(newListings, env.ALERT_TO));
      for (const listing of newListings) {
        ctx.waitUntil(requestDelisting(listing.target, listing.dnsbl, env.DB));
      }
    }
  },
};
```

---

## Automated Delisting Requests

```typescript
// src/blacklist/delisting.ts
import type { D1Database } from '@cloudflare/workers-types';

// Barracuda BRBL offers an automated removal API
const AUTO_DELIST_APIS: Partial<Record<string, (target: string) => Promise<string>>> = {
  'b.barracudacentral.org': async (ip: string) => {
    const res = await fetch(
      `https://www.barracudacentral.org/lookups/not-spam?ip=${encodeURIComponent(ip)}`,
      { method: 'GET' },
    );
    return await res.text();
  },
};

export async function requestDelisting(
  target: string,
  dnsbl: string,
  db: D1Database,
): Promise<void> {
  const fn = AUTO_DELIST_APIS[dnsbl];
  const method = fn ? 'api' : 'manual';
  let status = fn ? 'submitted' : 'requires-manual';
  let responseBody: string | null = null;

  if (fn) {
    try {
      responseBody = await fn(target);
    } catch (err) {
      status = 'error';
      responseBody = String(err);
    }
  }

  await db.prepare(
    `INSERT INTO delisting_requests (requested_at, target, dnsbl, method, status, response_body)
     VALUES (?, ?, ?, ?, ?, ?)`,
  )
    .bind(new Date().toISOString(), target, dnsbl, method, status, responseBody)
    .run();
}
```

---

## Alert Email

```typescript
// src/blacklist/alert.ts

export async function sendAlert(
  listings: { target: string; dnsbl: string; reason: string }[],
  alertTo: string,
): Promise<void> {
  const rows = listings
    .map((l) => `<tr><td>${l.target}</td><td>${l.dnsbl}</td><td>${l.reason}</td></tr>`)
    .join('');

  const html = `
    <h2>example project Blacklist Alert</h2>
    <p>${listings.length} new blacklist listing(s) detected:</p>
    <table border="1" cellpadding="4">
      <tr><th>Target</th><th>DNSBL</th><th>Reason</th></tr>
      ${rows}
    </table>
    <p>Check <code>blacklist_checks</code> in D1 for full history.</p>
  `;

  await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: alertTo }] }],
      from:    { email: 'alerts@example project.example.com', name: 'example project Alerts' },
      subject: `[URGENT] ${listings.length} IP/domain(s) blacklisted`,
      content: [{ type: 'text/html', value: html }],
    }),
  });
}
```

---

## Wrangler Config

```toml
# wrangler.toml
name = "blacklist-monitor"

[triggers]
crons = ["*/15 * * * *"]   # every 15 minutes

[[d1_databases]]
binding  = "DB"
database_name = "example project-email"
database_id   = "your-db-id"

[vars]
ALERT_TO        = "ops@example project.example.com"
SENDING_IPS     = "198.51.100.10,198.51.100.11"
SENDING_DOMAINS = "mail.example project.example.com,example project.example.com"
```

---

## Anti-patterns

- **Querying DNSBLs via plain DNS in Workers** — Workers have no raw UDP socket access.
  Always use DNS-over-HTTPS (DoH). Cloudflare's DoH endpoint is the most reliable
  inside the Workers network.
- **Alerting on every check cycle** — if an IP stays listed across 96 checks per day,
  you will receive 96 alerts. Track listings in D1 and alert only on *new* listings
  (i.e., the first time that (target, dnsbl) pair appears as listed within a 24-hour
  window).
- **Auto-submitting delisting to Spamhaus** — Spamhaus requires manual investigation
  and proof of remediation. Auto-submitting without fixing the root cause wastes the
  request and may result in a repeat listing faster.
- **Storing IPs in Worker environment variables** — use Worker secrets or D1 for
  the sending IP inventory so they can be updated without redeployment.

---

## Gotchas

- DoH returns NXDOMAIN via `Answer: []` (empty), not a 404. Check for empty array,
  not an error response.
- Barracuda BRBL delisting applies only to IPs, not domains. Domain-based DNSBLs
  (DBL, SURBL) require addressing the underlying content or domain reputation; no
  automated API exists.
- Some DNSBLs throttle repeated lookups from the same source IP. Cloudflare's egress
  IPs are shared; heavy polling can result in query rate limiting. Space checks to
  one per dnsbl every 15 minutes maximum.
- Spamhaus ZEN return code `127.0.0.10` (PBL) is **not** a spam listing — it simply
  indicates a dynamic/consumer IP. Do not alert or request delisting for PBL hits;
  the correct fix is to send through a dedicated relay.

---

## Verification

```bash
# Manually trigger the cron via Wrangler
wrangler dev --test-scheduled

# Check that the check was recorded
wrangler d1 execute DB --command \
  "SELECT * FROM blacklist_checks ORDER BY checked_at DESC LIMIT 20;"

# Simulate a listing by querying directly
curl "https://cloudflare-dns.com/dns-query?name=2.0.0.127.zen.spamhaus.org&type=A" \
  -H "accept: application/dns-json"
# Should return 127.0.0.2 confirming the DoH query works
```

---

## Related

- `email-blocklist-remediation.md`
- `email-dnsbl-realtime-blacklist-check-workers.md`
- `email-reputation-monitoring.md`
- `email-postmaster-api-workers-analytics-engine.md`
- `complaint-rate-monitoring.md`
- `spamtrap-types-avoidance.md`

---

## Sources

- Spamhaus ZEN return codes — https://www.spamhaus.org/zen/
- Barracuda BRBL lookup/removal — https://www.barracudacentral.org/
- Cloudflare DNS-over-HTTPS — https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/
- DNSBL.info overview — https://www.dnsbl.info/dnsbl-list.php
- Google Postmaster Tools — https://postmaster.google.com/

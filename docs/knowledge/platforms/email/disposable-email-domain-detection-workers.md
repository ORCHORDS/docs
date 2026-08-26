# Disposable Email Domain Detection at the Edge with Cloudflare Workers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Sign-up forms and transactional email flows are polluted by disposable (temporary) email addresses from services like Mailinator, Guerrilla Mail, and thousands of auto-generated domains. These addresses spike bounce rates, skew engagement metrics, inflate free-tier usage, and drain sending reputation. Blocking them at the database layer is too late—the row is already written, the welcome email already queued.

Catching disposable addresses at the **edge**, inside a Cloudflare Worker that handles form submissions or API registrations, eliminates the problem before any backend state is created, without adding a round-trip to a third-party API on every request.

---

## Context

Disposable email detection requires three complementary signals:

| Signal | What it catches |
|--------|----------------|
| Blocklist domain match | Known throwaway services (mailinator.com, yopmail.com, etc.) |
| MX record absence / null MX | Domains with no mail exchange—can never receive mail |
| Heuristic patterns | Auto-generated subdomains, single-character labels, numeric-only labels |

A Cloudflare Worker can run the blocklist check and heuristic check synchronously (zero latency). MX validation requires a DNS lookup—Workers' `fetch` supports DNS-over-HTTPS (DoH), keeping this inside the Worker without egress to an external SaaS.

The blocklist is stored in **KV** for sub-millisecond reads and refreshed from **R2** on a daily Cron Trigger without touching the Worker's deploy cycle.

---

## Architecture Overview

```
POST /api/register
        │
        ▼
  Cloudflare Worker
        │
        ├─ 1. Parse email, extract domain
        ├─ 2. KV blocklist lookup          (< 1 ms)
        ├─ 3. Heuristic pattern check      (sync)
        └─ 4. DoH MX record validation     (async, ~20 ms)
                │
                ▼
         Accept / Reject with 422
```

---

## Section 1: KV Blocklist Schema and Seeding

Store one key per domain. The value is a JSON object so future metadata (reason, added-date) can be appended without a schema migration.

```typescript
// scripts/seed-blocklist.ts
import { readFileSync } from "fs";

// Source: https://github.com/disposable-email-domains/disposable-email-domains
const domains: string[] = readFileSync("disposable_email_blocklist.conf", "utf8")
  .split("\n")
  .map((d) => d.trim().toLowerCase())
  .filter(Boolean);

// Run once: wrangler kv:bulk put --namespace-id=<ID> blocklist.json
const entries = domains.map((domain) => ({
  key: `blocklist:${domain}`,
  value: JSON.stringify({ reason: "known-disposable", addedAt: new Date().toISOString() }),
}));

console.log(JSON.stringify(entries));
```

Wrangler config:

```toml
# wrangler.toml
name = "email-guard"
main = "src/index.ts"
compatibility_date = "2026-01-01"

[[kv_namespaces]]
binding = "DISPOSABLE_KV"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

[[r2_buckets]]
binding = "BLOCKLIST_R2"
bucket_name = "email-blocklist-store"

[triggers]
crons = ["0 3 * * *"]   # refresh blocklist daily at 03:00 UTC
```

---

## Section 2: Daily Blocklist Refresh from R2

A Cron Trigger fetches the latest blocklist from R2 (where a separate pipeline drops updated files) and writes them into KV in batches.

```typescript
// src/refresh.ts
import type { KVNamespace, R2Bucket } from "@cloudflare/workers-types";

export interface Env {
  DISPOSABLE_KV: KVNamespace;
  BLOCKLIST_R2: R2Bucket;
}

export async function refreshBlocklist(env: Env): Promise<void> {
  const obj = await env.BLOCKLIST_R2.get("disposable_email_blocklist.conf");
  if (!obj) {
    console.error("Blocklist file not found in R2");
    return;
  }

  const text = await obj.text();
  const domains = text
    .split("\n")
    .map((d) => d.trim().toLowerCase())
    .filter(Boolean);

  // KV bulk write — 10 000 keys per batch is safe under the 25 MiB limit
  const BATCH_SIZE = 5_000;
  for (let i = 0; i < domains.length; i += BATCH_SIZE) {
    const batch = domains.slice(i, i + BATCH_SIZE);
    await Promise.all(
      batch.map((domain) =>
        env.DISPOSABLE_KV.put(
          `blocklist:${domain}`,
          JSON.stringify({ reason: "known-disposable", refreshedAt: new Date().toISOString() }),
          { expirationTtl: 60 * 60 * 48 } // expire in 48 h if refresh fails
        )
      )
    );
  }

  console.log(`Blocklist refreshed: ${domains.length} domains`);
}
```

---

## Section 3: Heuristic Pattern Detection

Catch auto-generated domains that aren't on any static list.

```typescript
// src/heuristics.ts

const SUSPICIOUS_PATTERNS: RegExp[] = [
  /^\d+\.[a-z]{2,4}$/,              // all-numeric label: 1234567.com
  /^[a-z]{1,2}\.[a-z]{2,4}$/,      // single/double char label: ab.net
  /trash|temp|fake|disposable|throw|noreply|mailnull/i,
  /\d{6,}/, // label with 6+ consecutive digits
];

export function isHeuristicallySuspicious(domain: string): boolean {
  return SUSPICIOUS_PATTERNS.some((re) => re.test(domain));
}
```

---

## Section 4: MX Record Validation via DNS-over-HTTPS

Workers cannot use the system resolver, but `1.1.1.1/dns-query` is reachable from every Worker via the standard `fetch` API.

```typescript
// src/dns.ts

interface DnsResponse {
  Status: number;   // 0 = NOERROR
  Answer?: Array<{ type: number; data: string }>;
}

const DOH_URL = "https://cloudflare-dns.com/dns-query";
const MX_TYPE = 15;

export async function hasMxRecords(domain: string): Promise<boolean> {
  const url = new URL(DOH_URL);
  url.searchParams.set("name", domain);
  url.searchParams.set("type", "MX");

  const response = await fetch(url.toString(), {
    headers: { Accept: "application/dns-json" },
    // Workers have a 30 s wall-clock limit; cap DNS to 3 s
    signal: AbortSignal.timeout(3_000),
  });

  if (!response.ok) return true; // fail-open: don't block on DNS errors

  const json: DnsResponse = await response.json();

  // Status 3 = NXDOMAIN, no Answer = no MX records
  if (json.Status === 3) return false;
  const mxRecords = json.Answer?.filter((r) => r.type === MX_TYPE) ?? [];
  return mxRecords.length > 0;
}
```

---

## Section 5: Main Worker Handler

```typescript
// src/index.ts
import type { ExecutionContext } from "@cloudflare/workers-types";
import { refreshBlocklist } from "./refresh";
import { isHeuristicallySuspicious } from "./heuristics";
import { hasMxRecords } from "./dns";

export interface Env {
  DISPOSABLE_KV: KVNamespace;
  BLOCKLIST_R2: R2Bucket;
  MX_CHECK_ENABLED: string; // "true" | "false" — toggle via env var
}

function extractDomain(email: string): string | null {
  const at = email.lastIndexOf("@");
  if (at < 1) return null;
  return email.slice(at + 1).toLowerCase().trim();
}

interface ValidationResult {
  allowed: boolean;
  reason?: string;
}

async function validateEmail(email: string, env: Env): Promise<ValidationResult> {
  if (!email || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    return { allowed: false, reason: "invalid-format" };
  }

  const domain = extractDomain(email);
  if (!domain) return { allowed: false, reason: "invalid-format" };

  // 1. KV blocklist (sub-millisecond)
  const hit = await env.DISPOSABLE_KV.get(`blocklist:${domain}`);
  if (hit !== null) return { allowed: false, reason: "known-disposable" };

  // 2. Heuristic patterns (synchronous)
  if (isHeuristicallySuspicious(domain)) {
    return { allowed: false, reason: "suspicious-pattern" };
  }

  // 3. MX check (async, ~20 ms — skip if disabled)
  if (env.MX_CHECK_ENABLED === "true") {
    const hasMx = await hasMxRecords(domain);
    if (!hasMx) return { allowed: false, reason: "no-mx-record" };
  }

  return { allowed: true };
}

export default {
  async fetch(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const body = await request.json<{ email: string }>();
    const result = await validateEmail(body.email ?? "", env);

    if (!result.allowed) {
      return Response.json(
        { error: "email_rejected", reason: result.reason },
        { status: 422 }
      );
    }

    // Proceed to origin — proxy the request
    return fetch(request);
  },

  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    await refreshBlocklist(env);
  },
};
```

---

## Section 6: Role-Based and Sub-Addressing Normalization

Before domain extraction, normalize the local part to avoid bypass tricks:

```typescript
// src/normalize.ts

const ROLE_ACCOUNTS = new Set([
  "abuse", "admin", "billing", "contact", "help",
  "info", "mailer-daemon", "noreply", "no-reply",
  "postmaster", "root", "sales", "security", "support",
  "webmaster",
]);

export function normalizeEmail(raw: string): {
  normalized: string;
  isRoleAccount: boolean;
} {
  const lower = raw.toLowerCase().trim();
  const at = lower.lastIndexOf("@");
  if (at < 0) return { normalized: lower, isRoleAccount: false };

  let local = lower.slice(0, at);
  const domain = lower.slice(at + 1);

  // Strip plus-addressing  (user+tag@domain → user@domain)
  const plusIdx = local.indexOf("+");
  if (plusIdx > 0) local = local.slice(0, plusIdx);

  // Gmail dot trick (g.o.o.g.l.e → google)
  if (domain === "gmail.com" || domain === "googlemail.com") {
    local = local.replace(/\./g, "");
  }

  return {
    normalized: `${local}@${domain}`,
    isRoleAccount: ROLE_ACCOUNTS.has(local),
  };
}
```

---

## Anti-Patterns

- **Regex-only detection** — regex catches known patterns; a new disposable service with a normal-looking domain bypasses it entirely. Always combine blocklist + heuristics + MX.
- **Blocking on DNS timeout** — network latency spikes should not block sign-ups. Fail open (`return true`) on DNS errors and log the failure for review.
- **Storing the blocklist in Worker memory** — Workers are stateless; a 100 000-domain list in module scope bloats cold-start time significantly. Use KV.
- **Over-blocking with heuristics** — "disposable" patterns match legitimate company domains. Use heuristics as a soft signal; only hard-block on confirmed blocklist hits.
- **Skipping normalization** — `user+test@gmail.com` and `user@gmail.com` are the same mailbox. A user who creates multiple accounts via plus-addressing bypasses per-address limits.

---

## Gotchas

- **KV eventual consistency** — after seeding or refreshing the blocklist, reads from other Workers may return stale data for up to 60 seconds. This is acceptable for blocklist enforcement.
- **Cloudflare Workers DNS resolution** — Workers do not resolve `localhost` or RFC 1918 addresses via DoH. Always use Cloudflare's `cloudflare-dns.com` endpoint, not an internal resolver.
- **AbortSignal.timeout** — available only with `compatibility_date = "2023-03-01"` or later. On older dates, implement a manual `Promise.race` with a timeout.
- **Rate-limit the MX check** — if a single deployment serves millions of sign-ups per day, DoH calls count toward Cloudflare's egress. Cache the MX result in KV with a 24-hour TTL keyed by domain.
- **False positives on new TLDs** — `.xyz`, `.top`, `.click` domains are disproportionately disposable, but many legitimate startups use them. Don't wholesale-block TLDs; rely on per-domain blocklist entries.

---

## Verification

```bash
# 1. Test KV lookup
curl -X POST https://email-guard.example.workers.dev/ \
  -H "Content-Type: application/json" \
  -d '{"email":"test@mailinator.com"}'
# Expected: 422 { "error": "email_rejected", "reason": "known-disposable" }

# 2. Test MX absence (use a domain with no MX)
curl -X POST https://email-guard.example.workers.dev/ \
  -H "Content-Type: application/json" \
  -d '{"email":"user@no-mx-domain.example"}'
# Expected: 422 { "error": "email_rejected", "reason": "no-mx-record" }

# 3. Test valid address
curl -X POST https://email-guard.example.workers.dev/ \
  -H "Content-Type: application/json" \
  -d '{"email":"valid@example.com"}'
# Expected: proxied to origin (200 or downstream response)

# 4. Check KV blocklist size
wrangler kv:key list --namespace-id=<ID> --prefix="blocklist:" | jq length
```

---

## Related

- `email-verification-otp-workers.md` — OTP-based verification after address acceptance
- `cloudflare-email-routing-workers.md` — routing inbound mail with Workers
- `email-list-hygiene.md` — ongoing hygiene after initial sign-up
- `suppression-list-management.md` — managing known-bad addresses post-send
- `email-verification-flow.md` — full double opt-in flow

---

## Sources

- [disposable-email-domains/disposable-email-domains](https://github.com/disposable-email-domains/disposable-email-domains) — community-maintained blocklist
- [Cloudflare Workers KV documentation](https://developers.cloudflare.com/kv/)
- [DNS-over-HTTPS (RFC 8484)](https://datatracker.ietf.org/doc/html/rfc8484)
- [Cloudflare DNS-over-HTTPS resolver](https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/)
- [RFC 5321 §2.3.5 — Domain syntax](https://datatracker.ietf.org/doc/html/rfc5321#section-2.3.5)
- [RFC 7505 — Null MX](https://datatracker.ietf.org/doc/html/rfc7505)

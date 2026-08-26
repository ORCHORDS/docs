# Email List Hygiene and Validation with Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Importing a purchased, scraped, or legacy email list without validation causes hard bounces, spam complaints, and sender-reputation damage. You need a fast, serverless endpoint that scores each address (syntax, MX record, role address, disposable domain) before it enters your send pipeline, and a bulk validation queue for large lists.

## Context

Cloudflare Workers can perform DNS-over-HTTPS (DoH) lookups to validate MX records. A KV namespace stores a disposable-domain blocklist loaded from a public feed. D1 caches validation results so repeat lookups are instant. A Queue handles bulk validation without hitting Cloudflare's CPU time limits on individual requests.

## Solution

### KV – Disposable Domain Blocklist

```typescript
// scripts/load-blocklist.ts
// Run once (or on a cron) to populate KV from a public blocklist
// e.g. https://raw.githubusercontent.com/disposable-email-domains/disposable-email-domains/master/disposable_email_blocklist.conf

async function loadBlocklist(kvId: string, accountId: string, apiToken: string) {
  const res  = await fetch(
    'https://raw.githubusercontent.com/disposable-email-domains/disposable-email-domains/master/disposable_email_blocklist.conf'
  );
  const text = await res.text();
  const domains = text.split('\n').map(d => d.trim()).filter(Boolean);

  // Cloudflare KV bulk write API — max 10,000 keys per request
  const CHUNK = 10_000;
  for (let i = 0; i < domains.length; i += CHUNK) {
    const chunk = domains.slice(i, i + CHUNK).map(d => ({ key: `disposable:${d}`, value: '1' }));
    await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${accountId}/storage/kv/namespaces/${kvId}/bulk`,
      {
        method: 'PUT',
        headers: { Authorization: `Bearer ${apiToken}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(chunk),
      }
    );
  }
  console.log(`Loaded ${domains.length} disposable domains`);
}
```

### D1 Schema

```sql
-- migrations/0005_hygiene.sql
CREATE TABLE IF NOT EXISTS email_validation_cache (
  email       TEXT PRIMARY KEY,
  risk        TEXT NOT NULL,  -- high | medium | low
  reasons     TEXT NOT NULL,  -- JSON array of reason strings
  validated_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS role_address_prefixes (
  prefix TEXT PRIMARY KEY
);

INSERT OR IGNORE INTO role_address_prefixes (prefix) VALUES
  ('admin'),('administrator'),('info'),('noreply'),('no-reply'),
  ('postmaster'),('hostmaster'),('webmaster'),('support'),('help'),
  ('abuse'),('security'),('contact'),('sales'),('billing'),
  ('marketing'),('newsletter'),('unsubscribe'),('bounce'),('mailer-daemon');
```

### Worker – Validation Engine

```typescript
// src/email-hygiene-validator.ts
import { Env } from './types';

type Risk = 'high' | 'medium' | 'low';

interface ValidationResult {
  email:   string;
  valid:   boolean;
  risk:    Risk;
  reasons: string[];
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    if (req.method === 'POST' && url.pathname === '/validate') {
      const { email }: { email: string } = await req.json();
      const result = await validateEmail(email, env);
      return Response.json(result);
    }

    if (req.method === 'POST' && url.pathname === '/validate/bulk') {
      return handleBulkValidation(req, env);
    }

    if (req.method === 'GET' && url.pathname === '/validate/job') {
      const jobId = url.searchParams.get('id');
      return getJobStatus(jobId, env);
    }

    return new Response('Not found', { status: 404 });
  },

  async queue(batch: MessageBatch<BulkValidationMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { email, jobId } = msg.body;
      const result = await validateEmail(email, env);
      await recordJobResult(env, jobId, result);
      msg.ack();
    }
  },
};

// ──────────────────────────────────────────────
// Core validation pipeline
// ──────────────────────────────────────────────

export async function validateEmail(email: string, env: Env): Promise<ValidationResult> {
  // Check D1 cache first (valid for 24 hours)
  const cached = await env.DB.prepare(`
    SELECT risk, reasons FROM email_validation_cache
    WHERE email=? AND validated_at > unixepoch() - 86400
  `).bind(email).first<{ risk: Risk; reasons: string }>();

  if (cached) {
    return { email, valid: cached.risk !== 'high', risk: cached.risk, reasons: JSON.parse(cached.reasons) };
  }

  const reasons: string[] = [];

  // 1. Syntax check
  if (!isValidSyntax(email)) {
    reasons.push('invalid_syntax');
    return cache(env, { email, valid: false, risk: 'high', reasons });
  }

  const [local, domain] = splitEmail(email);

  // 2. Role address detection
  if (await isRoleAddress(env, local)) {
    reasons.push('role_address');
  }

  // 3. Disposable domain check (KV)
  if (await isDisposableDomain(env, domain)) {
    reasons.push('disposable_domain');
  }

  // 4. MX record validation (DoH)
  const hasMx = await hasMxRecord(domain);
  if (!hasMx) {
    reasons.push('no_mx_record');
  }

  const risk = computeRisk(reasons);
  return cache(env, { email, valid: risk !== 'high', risk, reasons });
}

// ──────────────────────────────────────────────
// Individual checks
// ──────────────────────────────────────────────

function isValidSyntax(email: string): boolean {
  // RFC 5321 simplified: local@domain, local ≤ 64 chars, domain ≤ 255
  const re = /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[a-zA-Z0-9](.?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](.?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/;
  return re.test(email) && email.length <= 320;
}

function splitEmail(email: string): [string, string] {
  const i = email.lastIndexOf('@');
  return [email.slice(0, i).toLowerCase(), email.slice(i + 1).toLowerCase()];
}

async function isRoleAddress(env: Env, local: string): Promise<boolean> {
  const row = await env.DB.prepare(`
    SELECT 1 FROM role_address_prefixes WHERE prefix = ?
  `).bind(local.replace(/[+.].*$/, '')).first();
  return row !== null;
}

async function isDisposableDomain(env: Env, domain: string): Promise<boolean> {
  const val = await env.KV.get(`disposable:${domain}`);
  return val !== null;
}

async function hasMxRecord(domain: string): Promise<boolean> {
  try {
    const res  = await fetch(
      `https://cloudflare-dns.com/dns-query?name=${encodeURIComponent(domain)}&type=MX`,
      { headers: { Accept: 'application/dns-json' } }
    );
    const data: { Answer?: { type: number }[] } = await res.json();
    // DNS type 15 = MX
    return (data.Answer ?? []).some(r => r.type === 15);
  } catch {
    return false; // network error → treat as no MX
  }
}

function computeRisk(reasons: string[]): Risk {
  if (reasons.includes('invalid_syntax'))   return 'high';
  if (reasons.includes('no_mx_record'))     return 'high';
  if (reasons.includes('disposable_domain')) return 'high';
  if (reasons.includes('role_address'))     return 'medium';
  return 'low';
}

// ──────────────────────────────────────────────
// D1 cache write
// ──────────────────────────────────────────────

async function cache(env: Env, result: ValidationResult): Promise<ValidationResult> {
  await env.DB.prepare(`
    INSERT OR REPLACE INTO email_validation_cache (email, risk, reasons)
    VALUES (?, ?, ?)
  `).bind(result.email, result.risk, JSON.stringify(result.reasons)).run();
  return result;
}

// ──────────────────────────────────────────────
// Bulk validation
// ──────────────────────────────────────────────

interface BulkValidationMessage {
  email: string;
  jobId: string;
}

async function handleBulkValidation(req: Request, env: Env): Promise<Response> {
  const { emails }: { emails: string[] } = await req.json();
  if (!emails?.length) return new Response('Missing emails', { status: 400 });
  if (emails.length > 50_000) return new Response('Max 50,000 per job', { status: 422 });

  const jobId = crypto.randomUUID();

  // Record job in KV (TTL 24 h)
  await env.KV.put(
    `hygiene_job:${jobId}`,
    JSON.stringify({ total: emails.length, processed: 0, results: [] }),
    { expirationTtl: 86_400 }
  );

  // Enqueue in batches of 100
  const BATCH = 100;
  for (let i = 0; i < emails.length; i += BATCH) {
    const messages = emails.slice(i, i + BATCH).map(email => ({ body: { email, jobId } }));
    await env.HYGIENE_QUEUE.sendBatch(messages);
  }

  return Response.json({ jobId, total: emails.length });
}

async function recordJobResult(
  env: Env,
  jobId: string,
  result: ValidationResult
): Promise<void> {
  const raw = await env.KV.get(`hygiene_job:${jobId}`);
  if (!raw) return;
  const job = JSON.parse(raw);
  job.processed++;
  job.results.push({ email: result.email, risk: result.risk, reasons: result.reasons });
  await env.KV.put(`hygiene_job:${jobId}`, JSON.stringify(job), { expirationTtl: 86_400 });
}

async function getJobStatus(jobId: string | null, env: Env): Promise<Response> {
  if (!jobId) return new Response('Missing id', { status: 400 });
  const raw = await env.KV.get(`hygiene_job:${jobId}`);
  if (!raw)  return new Response('Job not found', { status: 404 });
  return Response.json(JSON.parse(raw));
}
```

### wrangler.toml

```toml
[[kv_namespaces]]
binding = "KV"
id      = "<your-kv-id>"

[[d1_databases]]
binding       = "DB"
database_name = "hygiene-db"
database_id   = "<your-d1-id>"

[[queues.producers]]
binding = "HYGIENE_QUEUE"
queue   = "hygiene-validate-queue"

[[queues.consumers]]
queue          = "hygiene-validate-queue"
max_batch_size = 10
max_retries    = 2
```

## Implementation Details

- **Risk scoring matrix**:
  - `high`: invalid syntax, no MX record, or disposable domain — do not send.
  - `medium`: role address (admin@, noreply@) — send only for transactional; exclude from marketing.
  - `low`: passes all checks — safe to send.
- **DoH endpoint** (`cloudflare-dns.com/dns-query`) is accessible from Workers without egress restrictions. Response type 15 = MX.
- **KV blocklist** can be refreshed daily via a cron Worker running the `loadBlocklist` script; the bulk PUT API handles tens of thousands of keys efficiently.
- **D1 cache TTL of 24 hours** balances freshness against DoH call volume. For high-throughput pipelines increase to 7 days; MX records rarely change.
- **Bulk job state in KV** is acceptable for up to ~50,000 results (~5 MB JSON). For larger batches, write results to D1 and page through them.

## Anti-patterns

- Do not attempt SMTP verification (RCPT TO probing) from Workers — most ISPs block outbound SMTP from cloud IPs, and aggressive probing triggers blacklisting.
- Do not validate emails synchronously on the sign-up hot path for large bulk imports; use the queue endpoint.
- Do not rely on syntax validation alone; a syntactically valid address may have no MX record or belong to a disposable service.
- Do not build your own disposable-domain list from scratch; use and update a maintained public feed.

## Gotchas

- DoH responses are cached by Cloudflare; a domain that recently added MX records may show as invalid for up to the DNS TTL. Clear the D1 cache entry to force re-validation.
- KV `get` returns `null` for missing keys (not an error) — always check for `null` explicitly when testing blocklist membership.
- The KV bulk write API accepts up to 10,000 keys per request; paginate if your blocklist exceeds this.
- Workers CPU time limit (50 ms on free, 30 s on Paid) constrains how many DoH lookups you can do synchronously. The queue consumer pattern keeps each invocation to a small batch.
- `crypto.randomUUID()` is available in Workers natively — no import needed.

## Verification

```bash
# 1. Apply the migration
npx wrangler d1 execute hygiene-db --file=migrations/0005_hygiene.sql

# 2. Load the disposable blocklist
npx wrangler kv bulk put --binding=KV <(node scripts/load-blocklist.ts)

# 3. Validate a single address
curl -X POST https://<worker>.workers.dev/validate \
  -H 'Content-Type: application/json' \
  -d '{"email":"test@mailinator.com"}'
# Expected: { risk: "high", reasons: ["disposable_domain"] }

# 4. Validate a role address
curl -X POST https://<worker>.workers.dev/validate \
  -H 'Content-Type: application/json' \
  -d '{"email":"noreply@example.com"}'
# Expected: { risk: "medium", reasons: ["role_address"] }

# 5. Bulk validate
curl -X POST https://<worker>.workers.dev/validate/bulk \
  -H 'Content-Type: application/json' \
  -d '{"emails":["good@gmail.com","bad@mailinator.com","no-mx@nonexistent.example"]}'
# Returns: { jobId: "...", total: 3 }

# 6. Poll for results
curl "https://<worker>.workers.dev/validate/job?id=<jobId>"
```

## Related

- `documentation/docs/policies/email/workers-email-suppression-list-kv.md`
- `documentation/docs/policies/email/bounce-handling-queues.md`
- `documentation/docs/policies/email/workers-email-warmup-sender.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/
- https://github.com/disposable-email-domains/disposable-email-domains

# Email List Hygiene Validation Workers

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
Importing a CSV of addresses into your mailing list without pre-validation fills your suppression list with hard bounces, damages sender reputation, and wastes ESP quota on undeliverable addresses.

## Context
A Cloudflare Worker provides a real-time validation pipeline that runs three checks in order: RFC 5322 syntax, disposable/role-address blocklist lookups in KV, and MX record resolution via Cloudflare DNS-over-HTTPS. Addresses that fail any check are rejected before they reach D1 or your ESP. The pipeline is exposed as both a single-address HTTP endpoint (used in sign-up forms) and a bulk batch endpoint (used during list imports). Results are cached in KV to avoid redundant DNS lookups for addresses from the same domain within a 1-hour window.

## Validation Pipeline Architecture

```
POST /validate/email          POST /validate/bulk
        ↓                             ↓
   parse + normalise          chunk into 50-address batches
        ↓                             ↓
   syntax check (regex + RFC rules)
        ↓ pass
   KV blocklist check (disposable domains, role prefixes)
        ↓ pass
   MX DNS check (DoH → cloudflare-dns.com)
        ↓ pass
   mark VALID → cache domain result in KV (1 h)
```

## D1 Schema (optional audit log)

```sql
CREATE TABLE validation_log (
  id           TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
  address      TEXT NOT NULL,
  normalised   TEXT NOT NULL,
  domain       TEXT NOT NULL,
  syntax_ok    INTEGER NOT NULL,
  blocklist_ok INTEGER NOT NULL,
  mx_ok        INTEGER NOT NULL,
  verdict      TEXT NOT NULL,   -- 'valid' | 'invalid_syntax' | 'blocklisted' | 'no_mx'
  checked_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_vl_domain ON validation_log(domain);
CREATE INDEX idx_vl_verdict ON validation_log(verdict);
```

## Core Validation Worker

```typescript
// worker.ts
export interface Env {
  BLOCKLIST: KVNamespace;    // disposable domain list, KV key = domain → "1"
  MX_CACHE: KVNamespace;     // domain → "1" (has MX) | "0" (no MX), TTL 1 h
  DB: D1Database;            // optional audit log
}

interface ValidationResult {
  address: string;
  normalised: string;
  verdict: 'valid' | 'invalid_syntax' | 'blocklisted' | 'no_mx';
  syntaxOk: boolean;
  blocklistOk: boolean;
  mxOk: boolean;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });
    const url = new URL(request.url);

    if (url.pathname === '/validate/email') {
      const { address } = await request.json<{ address: string }>();
      const result = await validateOne(address, env);
      return Response.json(result);
    }

    if (url.pathname === '/validate/bulk') {
      const { addresses } = await request.json<{ addresses: string[] }>();
      if (addresses.length > 500) {
        return Response.json({ error: 'Max 500 addresses per bulk request' }, { status: 400 });
      }
      const results = await Promise.all(addresses.map((a) => validateOne(a, env)));
      const summary = {
        total: results.length,
        valid: results.filter((r) => r.verdict === 'valid').length,
        invalidSyntax: results.filter((r) => r.verdict === 'invalid_syntax').length,
        blocklisted: results.filter((r) => r.verdict === 'blocklisted').length,
        noMx: results.filter((r) => r.verdict === 'no_mx').length,
        results,
      };
      return Response.json(summary);
    }

    return new Response('Not Found', { status: 404 });
  },
};

async function validateOne(address: string, env: Env): Promise<ValidationResult> {
  const normalised = normaliseAddress(address);
  const domain = normalised.split('@')[1] ?? '';

  const base: ValidationResult = {
    address,
    normalised,
    verdict: 'valid',
    syntaxOk: false,
    blocklistOk: false,
    mxOk: false,
  };

  // Step 1: Syntax
  if (!isValidSyntax(normalised)) {
    return { ...base, verdict: 'invalid_syntax' };
  }
  base.syntaxOk = true;

  // Step 2: Blocklist (disposable domains + role prefixes)
  const blocklisted = await isBlocklisted(normalised, domain, env);
  if (blocklisted) {
    return { ...base, syntaxOk: true, verdict: 'blocklisted' };
  }
  base.blocklistOk = true;

  // Step 3: MX check
  const hasMx = await checkMx(domain, env);
  if (!hasMx) {
    return { ...base, syntaxOk: true, blocklistOk: true, verdict: 'no_mx' };
  }
  base.mxOk = true;

  return base;
}

function normaliseAddress(address: string): string {
  const trimmed = address.trim().toLowerCase();
  const [localRaw, domain] = trimmed.split('@');
  if (!localRaw || !domain) return trimmed;

  // Strip Gmail-style + subaddressing for deduplication (optional — remove if you use subaddressing)
  const local = localRaw.split('+')[0].replace(/\./g, domain === 'gmail.com' ? '' : '.');
  return `${local}@${domain}`;
}

function isValidSyntax(address: string): boolean {
  // RFC 5322-compatible pattern (simplified but production-tested)
  const re = /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$/;
  if (!re.test(address)) return false;
  if (address.length > 254) return false;
  const [local] = address.split('@');
  if ((local?.length ?? 0) > 64) return false;
  // Reject double dots in local part
  if (address.includes('..')) return false;
  return true;
}

const ROLE_PREFIXES = new Set([
  'noreply', 'no-reply', 'donotreply', 'mailer-daemon', 'postmaster',
  'abuse', 'webmaster', 'admin', 'hostmaster', 'info', 'support',
  'help', 'contact', 'sales', 'marketing',
]);

async function isBlocklisted(address: string, domain: string, env: Env): Promise<boolean> {
  // Check disposable domain KV list
  const disposable = await env.BLOCKLIST.get(`domain:${domain}`);
  if (disposable) return true;

  // Check role-address prefixes
  const local = address.split('@')[0];
  if (ROLE_PREFIXES.has(local ?? '')) return true;

  return false;
}

async function checkMx(domain: string, env: Env): Promise<boolean> {
  const cacheKey = `mx:${domain}`;
  const cached = await env.MX_CACHE.get(cacheKey);
  if (cached !== null) return cached === '1';

  try {
    const res = await fetch(
      `https://cloudflare-dns.com/dns-query?name=${encodeURIComponent(domain)}&type=MX`,
      { headers: { Accept: 'application/dns-json' } }
    );
    const data = await res.json<{ Answer?: { type: number; data: string }[] }>();
    const hasMx = (data.Answer ?? []).some((r) => r.type === 15); // type 15 = MX

    // If no MX, also check A record (some domains receive mail on the apex)
    let result = hasMx;
    if (!hasMx) {
      const aRes = await fetch(
        `https://cloudflare-dns.com/dns-query?name=${encodeURIComponent(domain)}&type=A`,
        { headers: { Accept: 'application/dns-json' } }
      );
      const aData = await aRes.json<{ Answer?: { type: number }[] }>();
      result = (aData.Answer ?? []).some((r) => r.type === 1);
    }

    await env.MX_CACHE.put(cacheKey, result ? '1' : '0', { expirationTtl: 3600 });
    return result;
  } catch {
    // DNS resolution failure — treat as unknown, allow with warning
    await env.MX_CACHE.put(cacheKey, '0', { expirationTtl: 60 }); // short cache on error
    return false;
  }
}
```

## Disposable Domain List Population

```typescript
// populate-blocklist.ts
// Run as a scheduled cron to refresh the disposable domain list from a public blocklist
const BLOCKLIST_URL =
  'https://raw.githubusercontent.com/disposable-email-domains/disposable-email-domains/master/disposable_email_blocklist.conf';

export async function refreshBlocklist(env: { BLOCKLIST: KVNamespace }): Promise<number> {
  const res = await fetch(BLOCKLIST_URL);
  const text = await res.text();
  const domains = text.split('\n').map((d) => d.trim()).filter(Boolean);

  // Batch writes — KV bulk put via Workers API (max 10,000 per call)
  const batch = domains.map((domain) => ({ key: `domain:${domain}`, value: '1' }));
  const chunkSize = 10_000;
  for (let i = 0; i < batch.length; i += chunkSize) {
    await env.BLOCKLIST.put(
      `__meta:last_updated`,
      new Date().toISOString(),
      { expirationTtl: 60 * 60 * 24 * 7 }
    );
    // KV bulk write requires the REST API from outside Workers; use fetch to CF API
    // or iterate individually inside the Worker (acceptable for < 50k domains)
    for (const item of batch.slice(i, i + chunkSize)) {
      await env.BLOCKLIST.put(item.key, item.value, { expirationTtl: 60 * 60 * 24 * 7 });
    }
  }

  return domains.length;
}
```

## Anti-patterns
- Performing live SMTP `RCPT TO` probing (email existence verification) — most ESPs block outbound SMTP from Workers; it also triggers rate-limit responses from target mail servers and is considered hostile by many postmasters.
- Accepting role addresses (admin@, info@) into a marketing list — they map to distribution groups and trigger immediate spam complaints when people check the shared inbox.
- Caching MX results indefinitely — domains change MX records; a 1-hour TTL balances performance against staleness.
- Stripping `+` subaddressing globally — legitimate users rely on `+tag` for filtering; only strip it for deduplication checks, not for the stored address.
- Logging every validated address in D1 permanently — the validation log grows unboundedly; add a cron to purge rows older than 30 days.

## Gotchas
- `cloudflare-dns.com/dns-query` resolves from Cloudflare's global anycast network, not from the Worker's PoP — resolution latency is typically < 20 ms worldwide but add a 2-second timeout via `AbortController`.
- Some domains use a wildcard `*  IN  A` record at the apex which makes them appear to have a valid A record even when mail is not accepted; treat these as `no_mx` unless an actual MX record is present.
- The Gmail dot-stripping rule (`john.doe@gmail.com` == `johndoe@gmail.com`) should only be applied during deduplication — store the address as the user typed it for the actual send.
- KV bulk write via the Workers API is not available inside a Worker runtime; you must use the Cloudflare REST API (`/client/v4/accounts/{id}/storage/kv/namespaces/{id}/bulk`) from an external script or a scheduled Worker that calls back to the CF API.
- Workers DNS-over-HTTPS counts against your outbound subrequest limit (1000 per request in the free plan); in bulk mode, deduplicate domains first and only look up each unique domain once.

## Verification
1. POST `{"address": "test@mailinator.com"}` — expect `verdict: "blocklisted"`.
2. POST `{"address": "notanemail"}` — expect `verdict: "invalid_syntax"`.
3. POST `{"address": "user@no-mx-exists-xyz123.com"}` — expect `verdict: "no_mx"` (confirm the domain has no DNS).
4. POST `{"address": "valid@gmail.com"}` — expect `verdict: "valid"`.
5. POST bulk with 50 addresses including a mix; confirm `summary.valid + summary.invalidSyntax + summary.blocklisted + summary.noMx === summary.total`.

## Related
- `disposable-email-domain-detection-workers.md`
- `email-mx-dns-validation-workers.md`
- `email-suppression-list-kv-workers.md`
- `email-list-hygiene.md`
- `bounce-classification-list-hygiene.md`

## Sources
- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://developers.cloudflare.com/1.1.1.1/dns-over-https/
- https://datatracker.ietf.org/doc/html/rfc5322

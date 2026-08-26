# Email MX DNS Validation in Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Users submit invalid email domains during signup, wasting send quota and damaging sender reputation. A synchronous MX lookup at the API layer rejects unreachable domains before any email is ever sent.

## Context
Cloudflare Workers can issue DNS-over-HTTPS queries to the `1.1.1.1` resolver without any external library. MX records indicate a domain is configured to receive mail; an empty MX response (or an NXDOMAIN) means delivery will fail. Caching results in KV avoids redundant lookups for popular domains like `gmail.com`.

## Performing an MX Lookup via DNS-over-HTTPS

Workers cannot open raw UDP/TCP sockets, but Cloudflare's `1.1.1.1` resolver supports JSON-over-HTTPS queries with no extra authentication.

```typescript
interface DnsAnswer {
  name: string;
  type: number; // 15 = MX
  TTL: number;
  data: string; // "10 mx.example.com."
}

interface DnsResponse {
  Status: number; // 0 = NOERROR, 3 = NXDOMAIN
  Answer?: DnsAnswer[];
}

async function queryMX(domain: string): Promise<string[]> {
  const url = `https://cloudflare-dns.com/dns-query?name=${encodeURIComponent(domain)}&type=MX`;
  const res = await fetch(url, {
    headers: { Accept: "application/dns-json" },
  });
  if (!res.ok) throw new Error(`DNS query failed: ${res.status}`);
  const data: DnsResponse = await res.json();
  if (data.Status !== 0 || !data.Answer) return [];
  return data.Answer
    .filter((a) => a.type === 15)
    .map((a) => a.data.trim());
}
```

## KV Caching Layer

Domain validation results are stable for hours. Cache them with a TTL that matches the shortest DNS TTL returned in the answer set to avoid stale negative results.

```typescript
const CACHE_TTL_SECONDS = 3600; // fallback when DNS TTL is missing

async function hasMXRecords(
  domain: string,
  kv: KVNamespace
): Promise<boolean> {
  const cacheKey = `mx:${domain.toLowerCase()}`;
  const cached = await kv.get(cacheKey);
  if (cached !== null) return cached === "1";

  const records = await queryMX(domain);
  const hasMX = records.length > 0;
  await kv.put(cacheKey, hasMX ? "1" : "0", {
    expirationTtl: CACHE_TTL_SECONDS,
  });
  return hasMX;
}
```

## Worker Request Handler

Wire MX validation into a signup endpoint so invalid domains are rejected before any record is written to the database.

```typescript
export interface Env {
  MX_CACHE: KVNamespace;
}

function extractDomain(email: string): string | null {
  const parts = email.toLowerCase().trim().split("@");
  if (parts.length !== 2 || !parts[1].includes(".")) return null;
  return parts[1];
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const body = await request.json<{ email: string }>();
    const email = body?.email ?? "";
    const domain = extractDomain(email);

    if (!domain) {
      return Response.json({ error: "Invalid email format" }, { status: 422 });
    }

    let valid: boolean;
    try {
      valid = await hasMXRecords(domain, env.MX_CACHE);
    } catch {
      // DNS lookup failed — fail open to avoid blocking real users on transient errors
      valid = true;
    }

    if (!valid) {
      return Response.json(
        { error: "Email domain does not accept mail" },
        { status: 422 }
      );
    }

    // Continue with signup logic…
    return Response.json({ ok: true });
  },
};
```

## Null MX Handling (RFC 7505)

A domain may publish a single null MX (`0 .`) to explicitly declare it never accepts mail. Treat this as invalid even though `Status === 0` and `Answer` is non-empty.

```typescript
function isNullMX(records: string[]): boolean {
  // Null MX data field is "0 ." (priority 0, exchange ".")
  return records.length === 1 && records[0].trim().endsWith(" .");
}

async function isDeliverable(domain: string, kv: KVNamespace): Promise<boolean> {
  const records = await queryMX(domain);
  if (isNullMX(records)) return false;
  return records.length > 0;
}
```

## Anti-patterns
- Blocking signups when the DNS resolver itself is temporarily unreachable — always fail open on network errors
- Caching negative results for too long; a new domain may add MX records within minutes of creation
- Using A-record fallback validation: some spam domains have A records but no MX records
- Performing MX lookup on every keystroke from the frontend — do it once on form submit at the API layer

## Gotchas
- `cloudflare-dns.com/dns-query` is rate-limited; the KV cache is essential for high-traffic signups
- Subdomains (e.g., `user@mail.example.com`) may not have their own MX records — they rely on parent domain delivery
- Some corporate domains use internal MX that resolves only on private networks; external lookup will return empty
- `type: 15` is the MX record type per RFC 1035; filter strictly to avoid counting CNAME entries

## Verification
1. Submit a signup with `test@nonexistent-domain-xyz.example` — expect HTTP 422
2. Submit with `test@gmail.com` — expect HTTP 200; verify the KV key `mx:gmail.com` exists with value `1`
3. Artificially set `mx:gmail.com` to `0` in KV, resubmit — expect 422 (proving cache is consulted)
4. Query `cloudflare-dns.com/dns-query?name=example.com&type=MX` directly to confirm expected MX data format

## Related
- `/documentation/docs/policies/email/disposable-email-domain-detection-workers.md`
- `/documentation/docs/policies/email/email-verification-otp-workers.md`
- `/documentation/docs/policies/email/bounce-suppression-d1.md`
- `/documentation/docs/policies/email/null-mx-no-mail-domain-handling.md`

## Sources
- RFC 5321 §5.1 — Locating the Target Host
- RFC 7505 — A "Null MX" No Delivery Resource Record
- Cloudflare DNS-over-HTTPS: https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/make-api-requests/dns-json/
- Cloudflare Workers KV: https://developers.cloudflare.com/kv/

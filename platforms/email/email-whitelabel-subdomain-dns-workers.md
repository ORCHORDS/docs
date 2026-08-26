# Email Whitelabel Subdomain Cloudflare DNS Workers

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
You want customers to send email from `mail.theirdomain.com` using your platform's shared infrastructure, so all authentication records (SPF, DKIM, DMARC) appear under the customer's own domain rather than yours.

## Context
Cloudflare Workers can proxy DNS-level TXT record verification challenges and automate CNAME provisioning via the Cloudflare DNS API so customers complete whitelabel onboarding without touching their DNS panel manually. Each tenant gets an isolated DKIM selector, SPF include directive, and tracking subdomain. D1 stores provisioning state; KV caches verification status for fast header injection on outbound sends.

## Architecture Overview

```
Customer domain  →  CNAME  →  your sending subdomain  →  ESP (MailChannels / SendGrid)
                    TXT    →  SPF include
                    TXT    →  DKIM public key (selector per tenant)
                    CNAME  →  DMARC subdomain
Cloudflare Worker  →  DNS API  →  auto-provision records on tenant onboard
                   →  D1  →  store provisioning state + selector
                   →  KV  →  cache verification result (5 min TTL)
```

## D1 Schema

```sql
CREATE TABLE whitelabel_domains (
  id          TEXT PRIMARY KEY,        -- tenant_id
  domain      TEXT NOT NULL UNIQUE,    -- e.g. mail.customer.com
  selector    TEXT NOT NULL,           -- e.g. cf-wl-a3f9
  dkim_pub    TEXT NOT NULL,           -- base64 PEM public key
  dkim_priv   TEXT NOT NULL,           -- encrypted private key (KMS-wrapped)
  spf_include TEXT NOT NULL,           -- e.g. include:spf.yourdomain.com
  verified    INTEGER NOT NULL DEFAULT 0,  -- 0 | 1
  verified_at TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_wl_domain ON whitelabel_domains(domain);
```

## Provisioning Worker

```typescript
// worker.ts
import { Env } from './types';
import { generateKeyPair } from './crypto';

export interface Env {
  DB: D1Database;
  DOMAIN_CACHE: KVNamespace;
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string; // scoped to DNS:Edit on customer zones
}

interface ProvisionRequest {
  tenantId: string;
  customerDomain: string; // apex domain, e.g. "customer.com"
  customerZoneId: string; // Cloudflare zone ID they've granted access to
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/whitelabel/provision') {
      return handleProvision(request, env);
    }
    if (request.method === 'GET' && url.pathname === '/whitelabel/verify') {
      return handleVerify(request, env);
    }
    return new Response('Not Found', { status: 404 });
  },
};

async function handleProvision(request: Request, env: Env): Promise<Response> {
  const body = await request.json<ProvisionRequest>();
  const { tenantId, customerDomain, customerZoneId } = body;

  const selector = `cf-wl-${crypto.randomUUID().slice(0, 8)}`;
  const { publicKey, privateKey } = await generateKeyPair(); // RSA-2048 DKIM pair

  const spfInclude = `include:spf.yourdomain.com`;
  const sendingSubdomain = `mail.${customerDomain}`;

  // Insert provisioning record
  await env.DB.prepare(
    `INSERT INTO whitelabel_domains
       (id, domain, selector, dkim_pub, dkim_priv, spf_include)
     VALUES (?, ?, ?, ?, ?, ?)`
  ).bind(tenantId, sendingSubdomain, selector, publicKey, privateKey, spfInclude).run();

  // Push DNS records to customer's Cloudflare zone
  const cfBase = `https://api.cloudflare.com/client/v4/zones/${customerZoneId}/dns_records`;
  const headers = {
    Authorization: `Bearer ${env.CF_API_TOKEN}`,
    'Content-Type': 'application/json',
  };

  const records = [
    // SPF
    {
      type: 'TXT',
      name: sendingSubdomain,
      content: `"v=spf1 ${spfInclude} -all"`,
      ttl: 300,
    },
    // DKIM
    {
      type: 'TXT',
      name: `${selector}._domainkey.${customerDomain}`,
      content: `"v=DKIM1; k=rsa; p=${publicKey}"`,
      ttl: 300,
    },
    // DMARC
    {
      type: 'TXT',
      name: `_dmarc.${customerDomain}`,
      content: `"v=DMARC1; p=quarantine; rua=mailto:dmarc-reports@yourdomain.com; sp=reject; adkim=s; aspf=s"`,
      ttl: 300,
    },
    // Bounce/tracking subdomain CNAME
    {
      type: 'CNAME',
      name: sendingSubdomain,
      content: 'relay.yourdomain.com',
      ttl: 300,
      proxied: false,
    },
  ];

  const results: string[] = [];
  for (const record of records) {
    const res = await fetch(cfBase, {
      method: 'POST',
      headers,
      body: JSON.stringify(record),
    });
    const data = await res.json<{ success: boolean; errors: unknown[] }>();
    if (!data.success) {
      return Response.json({ error: 'DNS provisioning failed', details: data.errors }, { status: 502 });
    }
    results.push(`${record.type} ${record.name}`);
  }

  return Response.json({ tenantId, selector, sendingSubdomain, provisioned: results });
}

async function handleVerify(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const tenantId = url.searchParams.get('tenantId');
  if (!tenantId) return new Response('Missing tenantId', { status: 400 });

  // Cache hit
  const cached = await env.DOMAIN_CACHE.get(`verify:${tenantId}`);
  if (cached) return Response.json(JSON.parse(cached));

  const row = await env.DB.prepare(
    `SELECT domain, selector, dkim_pub, spf_include FROM whitelabel_domains WHERE id = ?`
  ).bind(tenantId).first<{ domain: string; selector: string; dkim_pub: string; spf_include: string }>();
  if (!row) return new Response('Not found', { status: 404 });

  // DNS resolution check via Cloudflare DNS-over-HTTPS
  const [spfOk, dkimOk] = await Promise.all([
    checkTxt(row.domain, `v=spf1`),
    checkTxt(`${row.selector}._domainkey.${row.domain.replace(/^mail\./, '')}`, `v=DKIM1`),
  ]);

  const result = { tenantId, domain: row.domain, spfOk, dkimOk, verified: spfOk && dkimOk };

  if (result.verified) {
    await env.DB.prepare(
      `UPDATE whitelabel_domains SET verified = 1, verified_at = datetime('now') WHERE id = ?`
    ).bind(tenantId).run();
  }

  await env.DOMAIN_CACHE.put(`verify:${tenantId}`, JSON.stringify(result), { expirationTtl: 300 });
  return Response.json(result);
}

async function checkTxt(name: string, prefix: string): Promise<boolean> {
  const res = await fetch(
    `https://cloudflare-dns.com/dns-query?name=${encodeURIComponent(name)}&type=TXT`,
    { headers: { Accept: 'application/dns-json' } }
  );
  const data = await res.json<{ Answer?: { data: string }[] }>();
  return (data.Answer ?? []).some((a) => a.data.includes(prefix));
}
```

## DKIM Key Generation Helper

```typescript
// crypto.ts
export async function generateKeyPair(): Promise<{ publicKey: string; privateKey: string }> {
  const keyPair = await crypto.subtle.generateKey(
    { name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256' },
    true,
    ['sign', 'verify']
  );
  const [pub, priv] = await Promise.all([
    crypto.subtle.exportKey('spki', keyPair.publicKey),
    crypto.subtle.exportKey('pkcs8', keyPair.privateKey),
  ]);
  return {
    publicKey: btoa(String.fromCharCode(...new Uint8Array(pub))),
    privateKey: btoa(String.fromCharCode(...new Uint8Array(priv))),
  };
}
```

## Anti-patterns
- Sharing a single DKIM selector across all tenants — a key compromise affects every customer simultaneously.
- Using proxied (orange-cloud) CNAME for the sending subdomain — ESPs require direct DNS resolution for bounce processing and SMTP relay.
- Storing unencrypted DKIM private keys in D1 — wrap them with Cloudflare's KMS or Workers Secrets before persisting.
- Creating DNS records with TTL 1 — propagation noise makes verification flaky; 300 s is the practical minimum.
- Auto-verifying without an actual DNS lookup — provisioning the record and marking `verified=1` in the same transaction means DMARC enforcement fires before DNS propagates.

## Gotchas
- The Cloudflare DNS API requires the customer to have granted your OAuth app `Zone:DNS:Edit` on their zone, not just read.
- SPF includes from your shared domain count against the customer's 10-lookup limit — document this and flatten if needed (see `email-spf-flattening-workers.md`).
- DMARC `adkim=s` (strict) requires the DKIM signing domain to exactly match the From header domain — make sure ESP is configured to sign with the customer's domain, not yours.
- DNS-over-HTTPS verification in Workers may return stale NXDOMAIN for up to 5 minutes after a record is created; add a retry with exponential backoff.
- The `mail.` subdomain CNAME and the SPF TXT record on the same node conflict in some validators — use `_spf.customerDomain` as the SPF node instead and set a CNAME on `mail.` for routing only.

## Verification
1. After provision, call `GET /whitelabel/verify?tenantId=<id>` and confirm `spfOk` and `dkimOk` are both `true`.
2. Send a test message through the whitelabel subdomain and check `Authentication-Results` header in the received copy.
3. Check Google Postmaster Tools for the customer domain — domain reputation should appear within 24 hours of first send.
4. Run `dig TXT mail.customer.com` and `dig TXT cf-wl-XXXX._domainkey.customer.com` to confirm records are live.
5. Verify DMARC pass rate in your aggregate report pipeline (see `dmarc-aggregate-report-analysis.md`).

## Related
- `email-spf-flattening-workers.md`
- `email-dkim-signing-mailchannels-workers.md`
- `dmarc-aggregate-report-analysis.md`
- `email-alias-routing-kv-workers.md`
- `cloudflare-email-routing-workers.md`

## Sources
- https://developers.cloudflare.com/api/resources/dns/subresources/records/methods/create/
- https://datatracker.ietf.org/doc/html/rfc6376
- https://developers.cloudflare.com/email-routing/

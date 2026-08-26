# Email SPF Macro Deployment via Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You run a multi-tenant SaaS where each customer sends email from your shared domain
(`mail.platform.example`) but you need per-customer SPF authorisation — or you host
thousands of sub-domains and can't maintain a separate SPF TXT record for each one.
Every time you add or remove a customer sending IP, you update dozens of DNS records,
burn SPF lookup budget, or hit the 10-DNS-lookup limit and start soft-failing legitimate
mail.

SPF macros solve this: a single `TXT` record can delegate authorisation decisions to
a per-sender DNS lookup that a Cloudflare Worker generates dynamically.

---

## Context

RFC 7208 §7 defines macro expansion inside SPF records. Common macros:

| Macro | Expands to |
|---|---|
| `%{i}` | Sending IP address |
| `%{s}` | `localpart@domain` (SMTP envelope sender) |
| `%{l}` | Local part of envelope sender |
| `%{d}` | Current domain being checked |
| `%{h}` | EHLO/HELO domain |
| `%{c}` | SMTP client IP (same as `%{i}` usually) |
| `%{r}` | Receiving host domain |

Transformers `r` (reverse), `URL-encode %{xu}`) and digit prefix `%{i4r}` (last 4
octets, reversed — classic for IP-in-subdomain lookups) are also supported.

### Classic per-IP SPF macro pattern

```
v=spf1 exists:%{i}.spf.platform.example ~all
```

When Outlook checks whether `198.51.100.42` is authorised to send for
`customer@platform.example`, it resolves `198.51.100.42.spf.platform.example`.
Your Worker (via Cloudflare DNS Custom Nameserver or a Workers DNS responder) answers
`127.0.0.2` (exists → pass) or NXDOMAIN (exists → neutral/fail).

This costs exactly **one** DNS lookup regardless of how many IPs you authorise.

---

## Workers as a DNS Responder

Cloudflare does not expose a native Workers DNS handler, but you can serve SPF macro
lookups through **Cloudflare for SaaS / Custom Hostnames + Workers** acting as an
authoritative DNS shim, or use a simple approach: delegate `spf.platform.example` to
a third-party authoritative DNS service whose records your Worker manages via the
Cloudflare DNS API.

The simpler pattern for most teams is the **DNS API approach**:

```
Workers Cron / API endpoint  →  Cloudflare DNS API
  create / delete A records under spf.platform.example
  each record = authorised IP → 127.0.0.2
```

### Worker: Manage SPF Macro DNS Records via Cloudflare DNS API

```typescript
// spf-macro-manager.ts

interface Env {
  CF_API_TOKEN: string;   // DNS Edit permission only
  CF_ZONE_ID: string;     // Zone for platform.example
  DB: D1Database;
}

const SPF_SUBDOMAIN = "spf.platform.example";

async function cfDNS(
  env: Env,
  method: "GET" | "POST" | "DELETE",
  path: string,
  body?: unknown
): Promise<Response> {
  return fetch(`https://api.cloudflare.com/client/v4${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${env.CF_API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
}

// Add an IP to the SPF macro whitelist
export async function authoriseIP(ip: string, env: Env): Promise<void> {
  const name = `${ip}.${SPF_SUBDOMAIN}`;
  const res = await cfDNS(env, "POST", `/zones/${env.CF_ZONE_ID}/dns_records`, {
    type: "A",
    name,
    content: "127.0.0.2",
    ttl: 300,
    comment: "spf-macro-authorised",
  });
  if (!res.ok) throw new Error(`DNS create failed: ${await res.text()}`);

  // Track in D1 so we can clean up later
  await env.DB.prepare(
    `INSERT OR IGNORE INTO spf_authorised_ips (ip, dns_name, created_at)
     VALUES (?, ?, unixepoch())`
  ).bind(ip, name).run();
}

// Remove an IP from the whitelist
export async function revokeIP(ip: string, env: Env): Promise<void> {
  // Find the DNS record ID
  const res = await cfDNS(
    env, "GET",
    `/zones/${env.CF_ZONE_ID}/dns_records?name=${ip}.${SPF_SUBDOMAIN}&type=A`
  );
  const data: { result: Array<{ id: string }> } = await res.json();
  for (const record of data.result) {
    await cfDNS(env, "DELETE", `/zones/${env.CF_ZONE_ID}/dns_records/${record.id}`);
  }
  await env.DB.prepare(
    `DELETE FROM spf_authorised_ips WHERE ip = ?`
  ).bind(ip).run();
}
```

### REST API Worker Handler

```typescript
// worker.ts
import { authoriseIP, revokeIP } from "./spf-macro-manager";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const ip = url.searchParams.get("ip");

    if (!ip || !isValidIP(ip)) {
      return new Response("invalid ip", { status: 400 });
    }

    if (request.method === "POST") {
      await authoriseIP(ip, env);
      return Response.json({ status: "authorised", ip });
    }
    if (request.method === "DELETE") {
      await revokeIP(ip, env);
      return Response.json({ status: "revoked", ip });
    }
    return new Response("method not allowed", { status: 405 });
  },
};

function isValidIP(ip: string): boolean {
  return /^(\d{1,3}\.){3}\d{1,3}$/.test(ip); // IPv4 only; extend for IPv6
}
```

### D1 Schema

```sql
CREATE TABLE IF NOT EXISTS spf_authorised_ips (
  ip         TEXT PRIMARY KEY,
  dns_name   TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
```

---

## SPF Record for the Sending Domain

```
v=spf1 exists:%{i}.spf.platform.example -all
```

Deploy this as the TXT record on `platform.example` (the domain in your SMTP
envelope sender). The `-all` hard-fail is safe because the macro lookup is your
sole authorisation mechanism — there are no additional `include:` chains to
accidentally orphan IPs.

---

## Per-Sender / Per-Customer Macros

For per-tenant authorisation (different customers allowed different IPs):

```
v=spf1 exists:%{l}.%{i}.spf.platform.example -all
```

DNS lookup becomes `newsletter.198.51.100.42.spf.platform.example` where
`newsletter` is the local part of the envelope sender. Modify the D1 schema:

```sql
CREATE TABLE IF NOT EXISTS spf_authorised_ips (
  tenant_local  TEXT NOT NULL,  -- e.g. "newsletter"
  ip            TEXT NOT NULL,
  dns_name      TEXT NOT NULL,
  created_at    INTEGER NOT NULL,
  PRIMARY KEY (tenant_local, ip)
);
```

---

## IPv6 SPF Macros

IPv6 addresses cannot be used directly as DNS label prefixes. Use the reversed
nibble format:

```
v=spf1 exists:%{i6r}.spf.platform.example -all
```

`%{i6r}` expands `2001:db8::1` to
`1.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.8.b.d.0.1.0.0.2.spf.platform.example`
(32 nibbles reversed with dots). DNS labels are max 63 chars each; this expansion
fits at ~63 chars for the nibble portion.

---

## Anti-patterns

- **Using `%{s}` in exists without strict local-part sanitisation** — the local part
  comes from the SMTP envelope sender which is attacker-controlled. An attacker could
  craft a sender that queries an arbitrary subdomain. Always use `%{l}` combined with
  a fixed tenant allow-list.
- **Removing the DNS TTL floor** — short TTLs (< 60 s) under high send volume can
  generate millions of DNS queries to Cloudflare's resolver. Use TTL ≥ 300 s.
- **Mixing macro records with `include:` chains** — the 10-lookup limit still applies
  to any `include:` directives. A macro `exists:` costs exactly 1 lookup total.
- **Not setting `~all` / `-all`** — the macro is useless without a qualifier on `all`.
  Use `-all` (hard fail) after macro-based records for best results.

---

## Gotchas

- `exists:` returns Pass only if the DNS query returns *any* A record; the content
  `127.0.0.2` is conventional but could be any valid IPv4.
- Some older receivers do not implement RFC 7208 macros. Check MX-Toolbox SPF checker
  for macro support before rolling out.
- Cloudflare DNS API propagation can take a few seconds. Add a small cache-miss
  grace period before hard-failing new IPs (use a `~all` soft-fail during rollout).
- Firewall the SPF macro management endpoint — it directly controls who can send mail
  as your domain.

---

## Verification

```bash
# Check SPF macro record is published
dig TXT platform.example +short

# Manually test macro expansion (replace with real sending IP)
dig A 198.51.100.42.spf.platform.example
# Should return 127.0.0.2 for authorised IPs, NXDOMAIN for others

# Full SPF check simulation
# mxtoolbox.com/spf.aspx?domain=platform.example
```

---

## Related

- `spf-record-setup.md` — baseline SPF record configuration
- `email-spf-flattening-workers.md` — flattening large include chains
- `spf-dkim-dmarc-alignment-debugging-workers.md` — alignment debugging
- `email-multitenant-sender-isolation-d1-workers.md` — per-tenant isolation

---

## Sources

- RFC 7208 §7 — SPF Macro Definitions
- RFC 7208 §5.7 — `exists` mechanism
- Cloudflare DNS API — `/zones/{zone_id}/dns_records`
- MXToolbox SPF Checker — macro expansion test

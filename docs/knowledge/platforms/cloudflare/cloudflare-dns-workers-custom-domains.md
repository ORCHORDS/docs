# cloudflare-dns-workers-custom-domains

**Issue:** Configuring Cloudflare DNS for Workers custom domains —
         routes vs custom domain API, wildcard routing, mobile vs
         desktop subdomain split, DNS propagation and Workers
         activation lag after a deployment
**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

`wrangler deploy` exits successfully but `curl api.example.com`
returns the origin server response instead of the Worker. Or the
mobile subdomain (`m.example.com`) hits the right Worker but
desktop (`www.example.com`) falls through to origin. Or after
switching from Routes to Custom Domains, a stale DNS response
still reaches the old origin for several minutes.

## Context

Cloudflare Workers can be bound to hostnames via two mechanisms:
**Routes** (legacy, pattern-based, attached to a zone) and
**Custom Domains** (modern, hostname-specific, managed as Worker
resources). The two mechanisms are not interchangeable — they
have different DNS record types, different inheritance of zone
settings, and different latencies for activation after deploy.

example project mobile/desktop routing uses subdomain splitting where
`m.example.com` serves the mobile Worker and `api.example.com`
serves the API Worker. Getting DNS right for each path requires
understanding which mechanism owns the record.

---

## Routes vs Custom Domains: Comparison

| Feature                          | Routes              | Custom Domains       |
|----------------------------------|---------------------|----------------------|
| DNS record created automatically | No (must pre-exist) | Yes (A/CNAME)        |
| SSL cert management              | Zone cert used      | Cert per hostname    |
| Pattern syntax                   | Glob (`*`)          | Exact hostname only  |
| Path matching                    | Yes (`/api/*`)      | No (host only)       |
| Falls through to origin          | Yes (no match)      | No (Worker only)     |
| Wildcard subdomains              | Yes                 | Enterprise only      |
| CNAME-able from external DNS     | No                  | No (zone must be CF) |
| Worker activation lag post-deploy| ~30 s typical       | ~60 s typical        |

---

## Custom Domains: Setup

```toml
# wrangler.toml — Custom Domain (recommended)
name = "api-worker"
main = "src/index.ts"
compatibility_date = "2025-10-01"

[[custom_domains]]
pattern = "api.example.com"

# For mobile
[[custom_domains]]
pattern = "m.example.com"
```

```bash
wrangler deploy
# → Creates AAAA/A record in CF DNS automatically
# → Provisions TLS certificate for api.example.com
# → Associates hostname with the Worker
```

The created DNS record is type A pointing to a Cloudflare anycast
address. It is automatically orange-clouded (proxied). You will
see it in the DNS tab of the zone dashboard labeled with the
Worker name.

---

## Routes: Setup

Routes bind a Worker to a URL pattern on a zone. The zone's DNS
must already have a record for the hostname (can be a dummy A
record pointing to 192.0.2.1 — an RFC 5737 documentation range —
since the Worker intercepts before hitting origin).

```toml
# wrangler.toml — Routes (for path-based binding)
name = "api-worker"
main = "src/index.ts"
compatibility_date = "2025-10-01"

# API paths via Worker, other paths to origin
[[routes]]
pattern   = "example.com/api/*"
zone_name = "example.com"

# Desktop Worker on separate host
[[routes]]
pattern   = "www.example.com/*"
zone_name = "example.com"
```

```bash
# Create the required DNS record (one-time, if not already present)
# Dashboard → DNS → Add record
# Type: A  Name: www  Content: 192.0.2.1  Proxied: yes

wrangler deploy
# → Route pattern registered; DNS record must already exist
```

---

## Mobile vs Desktop Subdomain Routing

Two Workers, one zone. Requests to `m.example.com` must go to
the mobile Worker; requests to `api.example.com` go to the API
Worker. Use Custom Domains for clean separation:

```toml
# wrangler.toml — mobile-worker
name = "mobile-worker"
[[custom_domains]]
pattern = "m.example.com"
```

```toml
# wrangler.toml — api-worker
name = "api-worker"
[[custom_domains]]
pattern = "api.example.com"
```

Both Workers deployed independently. No route overlap is possible
because Custom Domains are exact-hostname matches.

For routing mobile vs desktop on the *same* hostname based on
User-Agent, use a single Worker with internal routing:

```ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const ua = request.headers.get("User-Agent") ?? "";
    const isMobile = /Mobi|Android|iPhone/i.test(ua);

    if (isMobile) {
      // Serve mobile SPA or proxy to mobile origin
      return env.MOBILE_WORKER.fetch(request);
    }
    return env.DESKTOP_WORKER.fetch(request);
  },
};
```

```toml
# Service bindings for the routing Worker
[[services]]
binding = "MOBILE_WORKER"
service = "mobile-worker"

[[services]]
binding = "DESKTOP_WORKER"
service = "desktop-worker"
```

---

## Wildcard Routes

Wildcard Custom Domains (e.g. `*.api.example.com`) require
Cloudflare Enterprise. On paid-non-enterprise plans, use
wildcard Route patterns instead:

```toml
# Wildcard route — matches any subdomain of api.example.com
[[routes]]
pattern   = "*.api.example.com/*"
zone_name = "example.com"
```

The Worker receives the full hostname in `request.url` and can
branch on it:

```ts
const url      = new URL(request.url);
const subdomain = url.hostname.split(".")[0]; // e.g. "v2", "beta"

if (subdomain === "v2") {
  return handleV2(request, env);
}
return handleV1(request, env);
```

---

## DNS Propagation and Workers Activation Lag

After `wrangler deploy`, two separate propagation events occur:

```
Event 1 — DNS record propagation
  Custom Domains create/update an A record in the CF zone.
  CF's own DNS resolves instantly (same network).
  External resolvers with cached TTL must wait for TTL expiry.
  Typical TTL for CF-managed records: 300 s (5 min) or 1 (auto).

Event 2 — Worker script propagation
  The Worker script propagates to CF edge PoPs globally.
  Typical activation lag: 30–90 s after `wrangler deploy` exits.
  During this window, some PoPs serve the old Worker version.
  Custom Domains lag slightly longer than Routes (~60 s vs ~30 s).
```

Mitigation:
- Use `wrangler versions upload` + gradual rollout for zero-lag
  canary deploys without the DNS-propagation risk.
- For critical hostname migrations, pre-create the DNS record
  with a low TTL (60 s) 24 h before the cutover.
- Monitor activation with `wrangler tail` — log entries appear
  only from PoPs that have the new version.

---

## Checking Active Routes and Custom Domains

```bash
# List current custom domains for a Worker
wrangler deployments list

# Check via API
curl "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID\
/workers/scripts/api-worker/domains" \
  -H "Authorization: Bearer $CF_TOKEN" | jq .

# Check routes
curl "https://api.cloudflare.com/client/v4/zones/$ZONE_ID\
/workers/routes" \
  -H "Authorization: Bearer $CF_TOKEN" | jq .

# Verify DNS record was created
curl "https://api.cloudflare.com/client/v4/zones/$ZONE_ID\
/dns_records?name=api.example.com" \
  -H "Authorization: Bearer $CF_TOKEN" | jq .result[].type
```

---

## Anti-patterns

- **Mixing Routes and Custom Domains for the same hostname.** A
  hostname with a Custom Domain will not match a Route pattern for
  the same path. Pick one mechanism per hostname.
- **Using Routes without a pre-existing DNS record.** The Worker
  is registered but requests to the hostname return NXDOMAIN or
  the zone's default behaviour; the Worker is never invoked.
- **Deploying Custom Domain Workers without waiting for cert
  provisioning.** Immediately after creation, HTTPS requests may
  get a self-signed or missing cert error (usually <2 min, but
  can take up to 15 min under load).
- **Setting long TTLs on apex records before a Worker cutover.**
  Long-cached DNS for the apex delays the migration globally.

## Gotchas

- Removing a Custom Domain from `wrangler.toml` and redeploying
  does NOT remove the DNS record. It must be removed manually in
  the CF dashboard or via API. The Worker detaches but the A
  record remains, pointing to a CF anycast address that now
  returns 1001 (no route).
- Workers custom domain certs renew automatically. If you have
  pinned the cert in a mobile app, the pin will break on renewal.
  Use SPKI pinning on the intermediate CA instead.
- Route patterns do not match the root zone. `example.com/*` will
  NOT match a request to `https://example.com/` without the path.
  Use `example.com/` (no wildcard) or `example.com*`.
- `workers_dev = false` disables the `.workers.dev` URL but does
  not disable the Custom Domain — the two are independent.

## Verification

```bash
# After deploy, confirm Worker is serving
curl -I https://api.example.com/
# → HTTP/2 200
# → CF-Worker: api-worker (header visible in some CF configs)

# Confirm DNS record type and proxy status
dig api.example.com
# → should resolve to CF anycast (104.x.x.x or 172.x.x.x)

# Check for activation lag
for i in $(seq 5); do
  curl -so /dev/null -w "%{http_code}" https://api.example.com/health
  sleep 10
done
# → all 200 within 90 s of deploy
```

## Related

- `cloudflare/workers-custom-domains.md`
- `cloudflare/workers-subdomain-routing.md`
- `cloudflare/workers-best-practices.md`
- `infra/wrangler-toml-multi-environment-config.md`
- `infra/dns-propagation-debugging.md`

## Source URLs

- https://developers.cloudflare.com/workers/configuration/
  routing/custom-domains/
- https://developers.cloudflare.com/workers/configuration/
  routing/routes/
- https://developers.cloudflare.com/fundamentals/
  manage-domains/add-dns-record/

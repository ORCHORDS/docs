# workers-custom-domains

**Issue:** Attaching a custom domain to a Cloudflare Worker instead of using workers.dev
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
By default Workers are accessible at `<name>.<subdomain>.workers.dev`. For production you usually want a custom domain (e.g. `api.example.com`). Cloudflare supports two approaches: **Custom Domains** (modern, recommended) and **Routes** (legacy, pattern-based).

## Pattern / Solution

**Option A — Custom Domains (recommended):**
```toml
# wrangler.toml
name = "my-api"
main = "src/index.ts"
compatibility_date = "2024-01-01"

# Attach to a hostname — domain must be in the same Cloudflare account
[[custom_domains]]
pattern = "api.example.com"

[[custom_domains]]
pattern = "api-staging.example.com"
```

```bash
wrangler deploy  # automatically creates DNS record + SSL cert
```

**Option B — Routes (for path-based routing on an existing zone):**
```toml
[[routes]]
pattern = "example.com/api/*"
zone_name = "example.com"
```

**Dashboard path:**
1. Workers & Pages → your Worker → Settings → Domains & Routes.
2. Click "Add Custom Domain" → enter hostname → Save.
3. Cloudflare creates an A/CNAME record and provisions a TLS certificate automatically.

**Checking active domains:**
```bash
wrangler deployments list
# or
curl "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/workers/scripts/$WORKER_NAME/routes" \
  -H "Authorization: Bearer $CF_TOKEN"
```

## Gotchas
- The domain **must** be on an active Cloudflare zone in the same account — you cannot use domains managed elsewhere.
- Custom Domains use `orange-cloud` (proxied) DNS; the Worker is the only origin — there is no fallback server.
- Routes (`example.com/api/*`) pass non-matching paths to the zone's existing origin; Custom Domains do not.
- Wildcard Custom Domains (`*.api.example.com`) are supported but require an Enterprise plan.
- Changing a Custom Domain requires re-deployment; the old domain stays active until removed.
- `workers.dev` subdomains can be disabled per-worker: `workers_dev = false` in `wrangler.toml`.
- TLS certificates for Custom Domains are automatically managed; no manual certificate needed.

## Related
- `workers-subdomain-routing.md`
- `workers-best-practices.md`
- `wrangler-toml-reference.md`

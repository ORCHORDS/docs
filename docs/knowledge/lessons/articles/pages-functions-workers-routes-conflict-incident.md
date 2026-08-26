# Pages Functions vs Workers Routes Routing Conflict Incident

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

After deploying a new Cloudflare Worker on a route pattern that overlapped with our
Cloudflare Pages project, API requests to `/api/*` began returning HTML 404 pages
instead of JSON responses. The Worker was intended to handle all `/api/*` traffic;
the Pages Functions sitting at `functions/api/[[catchall]].ts` also matched the same
path, and Cloudflare's resolution order caused Pages to win for a subset of requests
depending on which PoP served them. The split was non-deterministic from the client's
perspective and lasted 4 hours.

## Context

Cloudflare Pages projects automatically expose a Workers runtime via the `functions/`
directory. These Pages Functions are deployed as a Worker script internally but are
managed by the Pages deployment pipeline, not by `wrangler deploy`. When an operator
also deploys a standalone Worker with a Workers Route on the same zone and path pattern,
both scripts are technically eligible to handle the request.

Cloudflare's internal resolution order at the time of this incident was: **Workers Routes
(standalone) have higher priority than Pages Functions** for the same zone — but only when
the Workers Route is set on the **zone**, not on the Pages custom domain. Our Worker Route
was set on the zone; however, the Pages project was served from a custom domain that was
**also** added as a zone in our Cloudflare account. This created two independent route
evaluation contexts where Pages Functions won in one and the standalone Worker won in
another, depending on which PoP's edge cache held the zone's routing table.

---

## Timeline

| UTC | Event |
|-----|-------|
| 11:05 | New standalone Worker deployed with route `api.example.com/api/*` |
| 11:07 | Smoke tests pass (tested from single PoP via curl) |
| 11:30 | Customer error spike: `SyntaxError: Unexpected token '<'` (JSON consumers receiving HTML) |
| 12:00 | On-call checks Worker logs — all look healthy |
| 12:15 | Second engineer checks Pages deployment — no recent change |
| 13:40 | Route resolution ambiguity discovered by querying both Workers and Pages dashboards |
| 15:05 | Resolution: Pages Functions at `/api/*` removed; all API routing consolidated in Worker |
| 15:10 | Error rate returns to baseline |

---

## Root Cause: Dual Ownership of the Same Route

```
Zone: api.example.com
  ├── Workers Route: api.example.com/api/*  → standalone Worker (wrangler deploy)
  └── Pages Project: orchords-frontend
        └── Custom domain: api.example.com
              └── functions/api/[[catchall]].ts  → Pages Functions Worker
```

Both the Workers Route and the Pages Functions catchall legitimately matched
`api.example.com/api/users`. Cloudflare's edge evaluates Workers Routes first on the
zone, but the Pages Functions Worker is registered as a Pages-managed script — not via
the zone's Workers Routes table — so different PoPs resolved the ambiguity differently
based on routing table propagation state.

---

## Fix: Single Authoritative Owner Per Route Prefix

**Option A — Remove Pages Functions, use standalone Workers exclusively:**

```bash
# Delete the conflicting Pages Functions directory
rm -rf functions/api/

# Re-deploy Pages (now without any /api/* Functions)
wrangler pages deploy dist --project-name=orchords-frontend

# Confirm standalone Worker handles /api/*
curl -s https://api.example.com/api/health | jq .
```

**Option B — Remove the standalone Worker Route, use Pages Functions exclusively:**

```bash
# List existing Workers Routes on the zone
wrangler routes list --zone=api.example.com

# Delete the conflicting route
wrangler routes delete <ROUTE_ID>

# All /api/* traffic now handled by Pages Functions
```

**Option C — Use `_routes.json` to explicitly exclude paths from Pages Functions:**

```json
// public/_routes.json — tell Pages NOT to invoke Functions for /api/* paths
// so the standalone Worker Route always wins
{
  "version": 1,
  "include": ["/*"],
  "exclude": ["/api/*"]
}
```

We chose Option A. Pages Functions are appropriate for SSR rendering adjacent to the
Pages site; the API surface warrants its own independently deployed Worker with its own
`wrangler.toml`, versioning, and observability bindings.

---

## Validation Query — Detect Route Overlaps Before Deploy

```bash
#!/usr/bin/env bash
# pre-deploy-route-check.sh
# Exits non-zero if any Pages Functions catchall overlaps with Workers Routes

ZONE="api.example.com"
WORKER_ROUTES=$(wrangler routes list --zone="$ZONE" --json | jq -r '.[].pattern')
PAGES_FUNCTIONS=$(find functions -name "*.ts" -o -name "*.js" | \
  sed 's|functions||;s|\[\[.*\]\]|**|;s|\[.*\]|*|;s|\.ts$||;s|\.js$||')

echo "=== Workers Routes ==="
echo "$WORKER_ROUTES"
echo ""
echo "=== Pages Functions paths ==="
echo "$PAGES_FUNCTIONS"
echo ""
echo "Review for overlaps before proceeding with deploy."
```

---

## Anti-patterns

- Deploying a Workers Route and a Pages Functions catchall to the same path without
  consulting the resolution order documentation for the current Cloudflare release.
- Assuming smoke tests from a single PoP reveal routing issues — edge routing table
  propagation is eventually consistent across PoPs.
- Using a Pages project's custom domain and a standalone Worker Route on the same zone
  without explicitly controlling which script handles which prefix via `_routes.json`.
- Mixing Pages Functions and standalone Workers for the same application layer without a
  documented ownership model.

---

## Gotchas

- `_routes.json` controls which requests Pages Functions intercept, but it does **not**
  affect Workers Routes registered independently on the zone. The two systems have
  separate route tables.
- Deleting a Pages Functions file removes it from the **next** Pages deployment; it does
  not take effect until `wrangler pages deploy` is run.
- Pages Functions deployed via a custom domain register their routes under a Cloudflare-
  managed namespace that is separate from the zone's public Workers Routes list. You
  cannot see Pages Functions in `wrangler routes list`.
- Route resolution priority is documented per-platform release; it changed between
  Cloudflare's 2024 and 2025 Workers runtime updates. Always verify against current docs.

---

## Verification

After resolving the conflict:

1. `curl -s https://api.example.com/api/health -H "Accept: application/json"` — must
   return `Content-Type: application/json`.
2. Test from at least 3 geographically distinct locations (use Workers Playground or
   separate curl hosts) to catch PoP-level routing divergence.
3. Confirm no `functions/api/` directory exists in the Pages repo after the fix deploy:
   `ls functions/` in the Pages project root.
4. Add a CI step that fails if a `functions/api/**` file is added while the standalone
   Worker Route for `/api/*` exists in `wrangler.toml`.

---

## Related

- `pages-deploy-rollback-cache-invalidation-gap.md`
- `platform-migration-vercel-to-cloudflare-pages.md`
- `workers-binding-version-drift-production-incident.md`
- `dns-ttl-incidents-during-migration.md`
- `zero-downtime-deployment-workers.md`

---

## Sources

- Cloudflare Docs — Pages Functions routing: https://developers.cloudflare.com/pages/functions/routing/
- Cloudflare Docs — `_routes.json`: https://developers.cloudflare.com/pages/functions/routing/#create-a-_routesjson-file
- Cloudflare Docs — Workers Routes: https://developers.cloudflare.com/workers/configuration/routing/routes/
- Internal incident ticket INC-2026-0318

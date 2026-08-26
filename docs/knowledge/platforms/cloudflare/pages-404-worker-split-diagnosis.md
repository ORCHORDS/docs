# pages-404-worker-split-diagnosis

**Issue:** After splitting example project into three deployments (Pages for marketing+proxy, example project-functions Worker for user API, example project-admin Worker behind CF Access), the admin API went completely dead — endpoints returned 404 for six days (Aug 9-15) while everyone hunted for a missing route in the Worker code. The routes existed; the split had shipped NO TRAFFIC PATH to the admin Worker at all. Nobody noticed because "merged" was treated as "live".

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The diagnosis rules

1. **`/api/*` returning 404 on the public domain almost always means a broken/unrouted Pages deploy — not a missing route in the Worker.** The zone routing never reached the Worker; check the traffic path before the code.
2. **Map the zone routes explicitly.** In the 3-piece architecture only `api/streaming/*` (WebSockets) was a zone route; everything else rides Pages Functions/paths. A Worker with correct code and no ingress is a black box that 404s.
3. **A split is a migration of TRAFFIC, not just of code** — each new deployment needs: route/binding verified, auth layer (CF Access) verified, and a live probe confirming end-to-end.
4. **Six-day detection gap = no synthetic checks.** A daily authenticated probe of one admin endpoint would have caught it at minute one.
5. **The fix was found by verifying the LIVE path** (login 400 on bad input, guarded endpoints 401 without auth) — proving traffic now REACHES the Worker, before trusting any function-level behavior.

## The verification ladder (deploy → live)

1. **Build artifacts exist** — the deploy actually shipped the new Worker version.
2. **Route/binding exists** — dashboards/API show the zone route, custom domain, or service binding pointing at the Worker.
3. **Unauthenticated probe** — endpoint reachable (401/400/redirect is FINE; 404/522/1000 is not).
4. **Authenticated probe** — the auth layer (CF Access, JWT) passes and the endpoint answers semantically.
5. **Domain-level probe** — hit the PUBLIC hostname the split is supposed to serve; internal-only checks hide missing public paths.

## Architectural notes for multi-Worker splits

1. **One zone route per special path prefix** (e.g. WebSocket streaming), everything else via Pages proxy or service bindings — fewer zones routes, fewer silent black holes.
2. **Each Worker gets a health endpoint** that answers before auth (even a version string) — it makes the unreachable-vs-broken distinction instant.
3. **Deploy order matters:** ship traffic paths with the Worker, not after it; a Worker without ingress is invisible to users and half-invisible to monitoring.
4. **CF Access on admin planes is correct** — but probe THROUGH it (service token or test policy) so "Access is up, Worker is dead" is distinguishable from "both dead".
5. **Write the traffic-path map in the repo** (which hostname/prefix hits which deployment) — the six-day hunt happened because the map lived in nobody's head completely.

## Related

- `../deploy/merged-is-not-deployed-bundle-verification.md`
- `../frontend/build-time-env-baking-chunk-hash.md`

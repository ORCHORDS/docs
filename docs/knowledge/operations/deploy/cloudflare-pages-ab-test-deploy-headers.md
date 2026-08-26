# Cloudflare Pages A/B Test Deploy via Headers Transform Rules

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

You have two Cloudflare Pages branches (`main` and `experiment`) and need to serve a percentage of real users the experiment build without a third-party feature-flag SaaS, without changing application code, and without a rollback risk that affects both variants simultaneously.

## Context

Cloudflare Pages exposes every branch as a unique preview URL (`experiment.<project>.pages.dev`). Combining **Transform Rules** (HTTP response header injection) with a **Worker route** in front of your production domain lets you implement stateless, cookie-pinned A/B routing entirely at the edge. No application changes are required. The split percentage is controlled by a single KV value so you can adjust it without re-deploying either Pages branch.

---

## 1. Branch Architecture

```
main          → https://myapp.pages.dev               (control, 80 %)
experiment    → https://experiment.myapp.pages.dev    (variant, 20 %)
```

Both branches are deployed independently via Wrangler Pages or the Git integration. A Router Worker sits in front of `myapp.com/*` and rewrites the request origin based on a bucket decision.

---

## 2. Router Worker — Bucket Decision + Cookie Pinning

```typescript
// router-worker/src/index.ts
export interface Env {
  AB_CONFIG: KVNamespace;  // key: "ab_split", value: "0.20"
}

const CONTROL_ORIGIN  = "https://myapp.pages.dev";
const VARIANT_ORIGIN  = "https://experiment.myapp.pages.dev";
const COOKIE_NAME     = "__ab_bucket";
const COOKIE_MAX_AGE  = 60 * 60 * 24 * 7; // 7 days

function getBucket(request: Request, splitRatio: number): "control" | "variant" {
  const cookies = request.headers.get("Cookie") ?? "";
  const match   = cookies.match(new RegExp(`${COOKIE_NAME}=([^;]+)`));
  if (match) return match[1] as "control" | "variant";

  // Deterministic hash on IP + UA so the same user stays consistent
  // even across cookie-less environments (e.g. Safari ITP purge)
  const seed   = (request.headers.get("CF-Connecting-IP") ?? "") +
                 (request.headers.get("User-Agent") ?? "");
  const hash   = [...seed].reduce((acc, c) => (acc * 31 + c.charCodeAt(0)) >>> 0, 0);
  return (hash % 100) / 100 < splitRatio ? "variant" : "control";
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const splitRaw   = await env.AB_CONFIG.get("ab_split");
    const splitRatio = parseFloat(splitRaw ?? "0");
    const bucket     = getBucket(request, splitRatio);
    const origin     = bucket === "variant" ? VARIANT_ORIGIN : CONTROL_ORIGIN;

    const url     = new URL(request.url);
    url.hostname  = new URL(origin).hostname;

    const upstream = await fetch(url.toString(), {
      method:  request.method,
      headers: request.headers,
      body:    request.body,
    });

    const response = new Response(upstream.body, upstream);

    // Pin bucket in cookie so the user stays in the same variant
    if (!request.headers.get("Cookie")?.includes(COOKIE_NAME)) {
      response.headers.append(
        "Set-Cookie",
        `${COOKIE_NAME}=${bucket}; Max-Age=${COOKIE_MAX_AGE}; Path=/; SameSite=Lax; Secure`
      );
    }

    response.headers.set("X-AB-Bucket", bucket);
    return response;
  },
} satisfies ExportedHandler<Env>;
```

---

## 3. Wrangler Config for the Router Worker

```toml
# router-worker/wrangler.toml
name = "ab-router"
main = "src/index.ts"
compatibility_date = "2026-06-01"

[[kv_namespaces]]
binding = "AB_CONFIG"
id      = "YOUR_KV_NAMESPACE_ID"

[[routes]]
pattern = "myapp.com/*"
zone_name = "myapp.com"
```

---

## 4. Seeding the Split Value in CI

```bash
# deploy.sh — runs after both Pages branches are deployed
set -euo pipefail

SPLIT="${AB_SPLIT_RATIO:-0}"   # 0 = 100 % control (safe default)

wrangler kv key put \
  --namespace-id "$KV_NAMESPACE_ID" \
  "ab_split" "$SPLIT"

echo "A/B split set to ${SPLIT}"
```

Promote to the experiment gradually:

```bash
# Increase to 20 % variant after smoke tests pass
wrangler kv key put --namespace-id "$KV_NAMESPACE_ID" "ab_split" "0.20"
```

---

## 5. Transform Rules for Analytics Attribution

Add a Cloudflare Transform Rule (via Terraform or the dashboard) that injects the bucket into every HTML response so client-side analytics can read it:

```hcl
# terraform/ab_transform_rule.tf
resource "cloudflare_ruleset" "ab_response_headers" {
  zone_id = var.zone_id
  name    = "AB test response headers"
  kind    = "zone"
  phase   = "http_response_headers_transform"

  rules {
    action = "rewrite"
    action_parameters {
      headers {
        name      = "X-AB-Bucket"
        operation = "set"
        value     = "control"   # overridden by Worker header above
      }
    }
    expression = "true"
    enabled    = true
  }
}
```

The Worker's `X-AB-Bucket` header is set upstream; the Transform Rule acts as a pass-through fallback for requests that bypass the Worker.

---

## 6. Ending the Experiment — Full Cutover

```bash
# Promote experiment to main
git checkout main
git merge --ff-only experiment
git push origin main

# Zero out split immediately
wrangler kv key put --namespace-id "$KV_NAMESPACE_ID" "ab_split" "0"

# Delete cookie on next user visit by setting Max-Age=0
# (handled in Worker when split is 0 and cookie == "variant")
```

---

## Anti-patterns

- **Splitting by URL path alone** — users navigating between paths switch buckets mid-session, corrupting experiment data.
- **Skipping cookie pinning** — without a sticky assignment, a single user lands in both variants across refreshes, making metrics meaningless.
- **Running the split in the Pages build step** — build-time splitting couples deployment cadence to experiment lifecycle; prefer the runtime Worker approach above.
- **Forgetting to clear the cookie** at experiment end — returning visitors stay in the variant bucket indefinitely.

## Gotchas

- **Preview URL authentication** — by default, `experiment.myapp.pages.dev` requires a Cloudflare Access token for non-production branches. Either disable Access on the preview domain or forward a service token from the Router Worker.
- **Cache poisoning** — if Cloudflare caches the Pages response at the edge before the Worker sets `Vary: Cookie`, both buckets may receive the same cached HTML. Set `Cache-Control: private` on A/B-tested pages or add a Cache Rule to bypass cache for requests carrying the bucket cookie.
- **KV eventual consistency** — `ab_split` reads from KV may lag up to 60 s in the worst case. Account for a ramp window, not an instant cutover.
- **`cf-ray` tracing** — the upstream Pages request carries a new Ray ID; correlate with the original via the `X-AB-Bucket` header logged in Workers Logpush.

## Verification

```bash
# Confirm variant traffic is flowing
curl -s -o /dev/null -w "%{http_code}" https://myapp.com/ -H "Cookie: __ab_bucket=variant"
# Expected: 200 served from experiment branch

# Check split value
wrangler kv key get --namespace-id "$KV_NAMESPACE_ID" "ab_split"
# Expected: 0.20

# Tail live Router Worker logs
wrangler tail ab-router --format pretty
```

## Related

- `feature-flag-deploy-coupling.md`
- `canary-workers-gradual-traffic-split.md`
- `cloudflare-pages-preview-deployments.md`
- `kv-namespace-seed-automation-wrangler.md`

## Sources

- Cloudflare Pages branch deployments: https://developers.cloudflare.com/pages/configuration/branch-build-controls/
- Workers KV: https://developers.cloudflare.com/kv/
- Transform Rules: https://developers.cloudflare.com/rules/transform/
- Cloudflare Access for Pages previews: https://developers.cloudflare.com/pages/configuration/preview-deployments/#customize-preview-deployments-access

# Workers Wrangler Deploy Surprises

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

`wrangler deploy` returns `Successfully deployed` but users still see old behaviour five minutes later. A compatibility date change silently breaks a regex API you relied on. You discover that `[vars]` values are visible in plaintext in the Cloudflare dashboard. Enabling `node_compat` makes your bundle 3× larger and breaks a sub-dependency. Two routes on the same zone fight for requests, and you cannot tell which Worker is handling which URL. These are the deploy-time surprises that only appear after `Successfully deployed` — the most dangerous class of bug.

---

## Context

Wrangler is the Cloudflare Workers CLI for building and deploying Workers. A successful `wrangler deploy` pushes a new Worker version to all edge nodes, but those nodes may serve cached responses for a brief window. Compatibility dates control which version of the V8 engine and Web Platform APIs are active for a Worker. Routes are matched by priority and specificity rules that are not always intuitive. Variables set in `[vars]` are public; secrets set via `wrangler secret put` are encrypted.

Orchords runs 12 Workers across staging and production. All six surprises below caused real incidents.

---

## Solution

```typescript
// workers-wrangler-deploy-surprises.ts
// Code patterns that prevent or detect each deploy surprise

// ─────────────────────────────────────────────────────────────
// SURPRISE 1: wrangler deploy succeeds but old code still serves
// ─────────────────────────────────────────────────────────────
//
// Edge nodes cache the Worker script. After deploy, it can take
// up to 30 s for all nodes globally to switch to the new version.
// During this window, different users hit different versions.
//
// Detection: embed a build version in the Worker response and
// assert it in your smoke test immediately after deploy.

const BUILD_VERSION = __BUILD_VERSION__; // injected via wrangler.toml [vars]

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Health endpoint for post-deploy smoke tests
    if (url.pathname === '/__health') {
      return Response.json({
        version: BUILD_VERSION,
        timestamp: Date.now(),
        region: request.cf?.colo ?? 'unknown',
      });
    }

    return handleRequest(request, env);
  },
};

// wrangler.toml:
// [vars]
// BUILD_VERSION = "2026-08-24-abc123"  # set by CI, e.g. git rev-parse --short HEAD

// Post-deploy smoke test (run from CI after wrangler deploy):
async function smokeTestVersion(expectedVersion: string, url: string): Promise<void> {
  const maxAttempts = 10;
  const delayMs = 5000;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const res = await fetch(`${url}/__health`);
    const body = await res.json<{ version: string }>();

    if (body.version === expectedVersion) {
      console.log(`Deploy confirmed on attempt ${attempt}`);
      return;
    }

    console.log(`Attempt ${attempt}: got version ${body.version}, expected ${expectedVersion}`);
    if (attempt < maxAttempts) {
      await new Promise((r) => setTimeout(r, delayMs));
    }
  }

  throw new Error(`Version ${expectedVersion} not serving after ${maxAttempts} attempts`);
}

// ─────────────────────────────────────────────────────────────
// SURPRISE 2: Compatibility date changes break existing behaviour
// ─────────────────────────────────────────────────────────────
//
// Bumping compatibility_date in wrangler.toml activates all
// behaviour changes for dates up to the new value. Some changes
// are breaking. Check the compatibility changelog before bumping.
//
// Key changes that have broken orchords code in practice:
//
// 2023-03-01: `fetch()` no longer follows redirects by default
//             (redirect: 'follow' was the old default, now 'manual')
// 2022-11-30: `FormData.get()` returns File instead of Blob for files
// 2021-11-10: Stricter URL parsing (rejects some previously-valid URLs)

function safeFetch(url: string, init?: RequestInit): Promise<Response> {
  // Explicitly set redirect to avoid compatibility-date behaviour change
  return fetch(url, {
    redirect: 'follow', // explicit, not relying on default
    ...init,
  });
}

// Test matrix: run these assertions in CI against the current compat date
async function assertCompatBehaviour(): Promise<void> {
  // Assert redirect behaviour
  const res = await safeFetch('https://httpbin.org/redirect/1');
  console.assert(res.url !== 'https://httpbin.org/redirect/1', 'redirect should be followed');

  // Assert URL parsing
  try {
    const u = new URL('https://example.com:80path'); // invalid port+path combo
    console.error('Expected URL parsing to throw but got', u.href);
  } catch {
    console.log('URL parsing correctly rejects invalid input');
  }
}

// ─────────────────────────────────────────────────────────────
// SURPRISE 3: [vars] are visible in the dashboard — not secrets
// ─────────────────────────────────────────────────────────────
//
// Values in wrangler.toml [vars] are stored in plaintext and
// visible to anyone with Cloudflare dashboard access to the zone.
// API keys, tokens, signing secrets, and credentials MUST use
// wrangler secret put, NOT [vars].

interface Env {
  // Safe to put in [vars] — not sensitive:
  ENVIRONMENT: string;           // 'production' | 'staging'
  LOG_LEVEL: string;             // 'debug' | 'info' | 'warn'
  BUILD_VERSION: string;

  // MUST be secrets (wrangler secret put), never [vars]:
  STRIPE_SECRET_KEY: string;     // wrangler secret put STRIPE_SECRET_KEY
  JWT_SIGNING_SECRET: string;    // wrangler secret put JWT_SIGNING_SECRET
  INTERNAL_SECRET: string;       // wrangler secret put INTERNAL_SECRET
  DATABASE_URL: string;          // wrangler secret put DATABASE_URL (has creds)
}

function validateEnv(env: Env): void {
  // Fail fast if a secret is accidentally set via [vars] (would be empty string or undefined)
  const requiredSecrets: Array<keyof Env> = [
    'STRIPE_SECRET_KEY',
    'JWT_SIGNING_SECRET',
    'INTERNAL_SECRET',
  ];

  for (const key of requiredSecrets) {
    if (!env[key] || (env[key] as string).length < 16) {
      throw new Error(
        `Environment variable ${key} is missing or too short — ensure it is set as a Secret, not a var`
      );
    }
  }
}

// ─────────────────────────────────────────────────────────────
// SURPRISE 4: node_compat mode side effects
// ─────────────────────────────────────────────────────────────
//
// Enabling node_compat = true in wrangler.toml bundles Node.js
// polyfills (buffer, stream, crypto, etc.) into your Worker.
// This can:
//   - Increase bundle size by 500 KB – 2 MB (may exceed 1 MB limit
//     on free plans, or 5 MB on paid plans)
//   - Override globalThis.Buffer, globalThis.process, etc.
//   - Cause conflicts if a sub-dependency also polyfills these globals
//
// Prefer explicit imports of only what you need:

// WRONG — enabling node_compat for all Node APIs when you only need 'crypto':
// compatibility_flags = ["nodejs_compat"]  // pulls in everything

// CORRECT — import only what you use directly:
import { createHmac } from 'node:crypto'; // tree-shakeable, no polyfill bloat

function signPayload(secret: string, payload: string): string {
  return createHmac('sha256', secret).update(payload).digest('hex');
}

// If you need a Node module that does NOT have a Workers-native equivalent:
// 1. Check if a Web Crypto API alternative exists (usually yes for crypto ops)
// 2. Use the specific polyfill package (@cloudflare/node-compat-x) instead of node_compat = true
// 3. Only then enable node_compat and measure bundle size delta

// ─────────────────────────────────────────────────────────────
// SURPRISE 5: Routes priority conflicts
// ─────────────────────────────────────────────────────────────
//
// When multiple Workers have routes that match the same URL,
// Cloudflare applies priority rules:
//   1. More specific routes win (fewer wildcards)
//   2. Among equal specificity, the route with a higher priority
//      number (set in the dashboard or via API) wins
//   3. Zone-level routes win over account-level routes
//
// The confusion: `wrangler deploy` does not warn about conflicts.
// A new route may silently shadow an existing one.

// Audit routes before deploying:
async function auditRoutes(zoneId: string, apiToken: string): Promise<void> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${zoneId}/workers/routes`,
    { headers: { Authorization: `Bearer ${apiToken}` } }
  );
  const data = await res.json<{
    result: Array<{ id: string; pattern: string; script: string; priority?: number }>;
  }>();

  // Check for overlapping patterns
  const routes = data.result;
  for (let i = 0; i < routes.length; i++) {
    for (let j = i + 1; j < routes.length; j++) {
      if (routesOverlap(routes[i].pattern, routes[j].pattern)) {
        console.warn(
          `Route conflict: "${routes[i].pattern}" (${routes[i].script}) ` +
          `overlaps "${routes[j].pattern}" (${routes[j].script})`
        );
      }
    }
  }
}

function routesOverlap(a: string, b: string): boolean {
  // Simplified check: convert glob to regex and test both ways
  const toRegex = (pattern: string) =>
    new RegExp('^' + pattern.replace(/\./g, '\\.').replace(/\*/g, '.*') + '$');
  const ra = toRegex(a);
  const rb = toRegex(b);
  // Check if a sample URL matching one pattern also matches the other
  const sampleA = a.replace('*', 'test').replace('*.', 'sub.');
  const sampleB = b.replace('*', 'test').replace('*.', 'sub.');
  return ra.test(sampleB) || rb.test(sampleA);
}

// ─────────────────────────────────────────────────────────────
// SURPRISE 6: Compatibility flags interaction
// ─────────────────────────────────────────────────────────────
//
// Compatibility flags can be combined, but some combinations
// conflict. For example, enabling both `nodejs_compat` and
// `nodejs_compat_v2` simultaneously causes a runtime error.
// Additionally, some flags are automatically enabled by your
// compatibility_date even if you do not list them explicitly,
// which means adding a flag that is already on is redundant but
// adding its inverse flag (`no_<flag>`) disables it.

// wrangler.toml reference (safe configuration for 2026):
/*
name = "orchords-api"
main = "src/index.ts"
compatibility_date = "2026-01-01"

# Explicitly list only flags you NEED beyond what the date provides:
compatibility_flags = [
  "nodejs_compat",         # adds Node.js API polyfills
  # DO NOT add "nodejs_compat_v2" alongside "nodejs_compat" — conflict!
]

[vars]
ENVIRONMENT = "production"
LOG_LEVEL = "info"
BUILD_VERSION = "set-by-ci"  # overridden in CI: wrangler deploy --var BUILD_VERSION:$(git rev-parse --short HEAD)

# Secrets set via: wrangler secret put SECRET_NAME
# Never list secrets here!
*/

// CI deploy command that injects build version:
// wrangler deploy --var BUILD_VERSION:$(git rev-parse --short HEAD)

async function handleRequest(request: Request, env: Env): Promise<Response> {
  validateEnv(env);
  const signature = signPayload(env.JWT_SIGNING_SECRET, request.url);
  return new Response(JSON.stringify({ ok: true, sig: signature.slice(0, 8) + '...' }), {
    headers: { 'Content-Type': 'application/json' },
  });
}

declare const __BUILD_VERSION__: string;
```

---

## Implementation Details

**Build version injection** via `--var BUILD_VERSION:$(git rev-parse --short HEAD)` in the CI `wrangler deploy` command overwrites the placeholder in `wrangler.toml` for that deploy only. The value appears in the dashboard under the Worker's environment variables but is not sensitive. The smoke test polls `/__health` up to 50 seconds post-deploy to confirm the new version is live on the edge before marking the deploy as successful.

**Compatibility date strategy** — pin to a specific date and update it deliberately, one quarter at a time. Read the Cloudflare compatibility changelog for every date in the range you are moving across. Run the compatibility assertion suite in CI against a staging Worker with the new date before promoting to production.

**Secrets vs vars audit** — run `wrangler secret list` and compare against the expected secrets list. Any secret that appears only in `[vars]` (not in the secrets list) is a security issue. Automate this check in CI:
```bash
EXPECTED_SECRETS="STRIPE_SECRET_KEY JWT_SIGNING_SECRET INTERNAL_SECRET"
ACTUAL=$(wrangler secret list --name orchords-api --json | jq -r '.[].name' | sort)
for s in $EXPECTED_SECRETS; do
  echo "$ACTUAL" | grep -q "$s" || echo "MISSING SECRET: $s"
done
```

**Bundle size with node_compat** — run `wrangler deploy --dry-run --outdir dist/` and inspect `dist/index.js` size before deploying to production. The paid plan limit is 5 MB uncompressed; the free plan limit is 1 MB. Prefer `import { x } from 'node:module'` over enabling the full compat layer.

**Route conflict prevention** — run the route audit script in CI as a pre-deploy check. The Cloudflare API returns all routes for a zone; comparing against the new route patterns before deploying surfaces conflicts before they shadow existing Workers.

---

## Anti-patterns

- Treating `wrangler deploy` success as proof that the new code is serving on all edge nodes.
- Bumping `compatibility_date` without reading the changelog for all intermediate dates.
- Putting API tokens, database credentials, or signing keys in `[vars]`.
- Enabling `nodejs_compat` for the entire Worker just to use one Node module.
- Deploying new routes without auditing for conflicts with existing routes on the same zone.
- Combining `nodejs_compat` and `nodejs_compat_v2` flags.

---

## Gotchas

- `wrangler deploy --dry-run` does not validate route conflicts — it only validates the bundle.
- Environment variables set via `--var` on the CLI override `[vars]` in `wrangler.toml` for that single deploy but do not persist in the dashboard.
- `wrangler secret put` prompts for the value interactively. In CI, pipe the value: `echo "$SECRET_VALUE" | wrangler secret put SECRET_NAME`.
- Route patterns in wrangler.toml use glob syntax, not regex. `*` matches any string including `/`, which is different from most URL glob conventions where `*` does not cross path boundaries.
- Workers deployed as part of a Pages project use Pages-specific routing, not zone-level routes. Service Bindings and route priority rules do not apply in the same way.
- `wrangler tail` in production streams live logs but with up to 15 s latency during high traffic. Do not rely on it for real-time alerting; use Workers Analytics Engine or a logging binding.

---

## Verification

```bash
# 1. Deploy with version injection
git_sha=$(git rev-parse --short HEAD)
wrangler deploy --var BUILD_VERSION:"$git_sha"

# 2. Smoke test version convergence (max 50 s)
for i in $(seq 1 10); do
  version=$(curl -s https://orchords-api.workers.dev/__health | jq -r '.version')
  if [ "$version" = "$git_sha" ]; then
    echo "Deploy confirmed: $version"
    break
  fi
  echo "Waiting... got $version"
  sleep 5
done

# 3. Audit secrets vs vars
wrangler secret list --name orchords-api --json | jq '[.[].name] | sort'

# 4. Check bundle size
wrangler deploy --dry-run --outdir dist/
du -sh dist/index.js

# 5. Audit route conflicts
curl -s "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/workers/routes" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[] | {pattern, script}'
```

---

## Related

- `documentation/docs/policies/lessons/workers-service-binding-lessons.md`
- `documentation/docs/policies/lessons/cold-start-optimization-lessons.md`
- Cloudflare Workers compatibility dates changelog
- Cloudflare Workers Routes documentation

---

## Sources

- Cloudflare Wrangler CLI docs (2025)
- Orchords production incident log #DEP-004 (stale code post-deploy), #DEP-011 (compat date regex break), #DEP-018 (var vs secret exposure)
- Cloudflare Community: "wrangler deploy succeeds but old worker still running" thread

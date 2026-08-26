# Feature Flag-Driven UI Injection via HTMLRewriter

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to roll out new UI features to a percentage of users, run A/B experiments, and let QA override flags via a cookie — all without a client-side SDK that adds JavaScript weight and flicker. Evaluating flags at the edge, before HTML reaches the browser, eliminates the "flash of wrong variant" and keeps feature-flag logic out of the client bundle.

## Context

Cloudflare KV stores flag definitions per segment. The Worker reads the requesting user's segment (from a JWT claim, cookie, or geo), looks up the applicable flags, and uses `HTMLRewriter` to inject or strip DOM elements before streaming the response to the browser. Percentage-based rollouts use a stable hash of the user ID so the same user always sees the same variant. QA teams can override any flag via a signed cookie.

## Solution

```typescript
// worker.ts — feature flag UI injection

export interface Env {
  FLAGS: KVNamespace;           // KV: key = flag name, value = FlagDefinition JSON
  FLAG_SIGNING_SECRET: string;  // secret for signing override cookies
  ORIGIN: Fetcher;              // upstream origin
}

// ---- Types ----

interface FlagDefinition {
  name: string;
  enabled: boolean;             // global kill switch
  rolloutPercent: number;       // 0–100; 100 = everyone
  segments: string[];           // user segments that qualify; empty = all
  variants: Record<string, FlagVariant>;
  defaultVariant: string;
}

interface FlagVariant {
  name: string;
  weight: number;               // relative weight for A/B split (sum of all weights)
  inject?: InjectionSpec[];     // elements to inject
  remove?: string[];            // CSS selectors of elements to remove
}

interface InjectionSpec {
  selector: string;             // CSS selector of target element
  position: 'prepend' | 'append' | 'before' | 'after' | 'replace';
  html: string;                 // raw HTML to inject
}

interface ResolvedFlags {
 variant: string; definition: FlagDefinition };
}

// ---- Worker entry point ----

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // Admin: clear override cookie
    if (url.pathname === '/__flags/clear') {
      return clearOverrideCookie();
    }

    // Admin: set override cookie (GET for simplicity; POST in production)
    if (url.pathname === '/__flags/override') {
      return setOverrideCookie(request, env);
    }

    const originResponse = await env.ORIGIN.fetch(request);
    const ct = originResponse.headers.get('Content-Type') ?? '';
    if (!ct.includes('text/html')) return originResponse;

    // Resolve flags for this request
    const userId = extractUserId(request);
    const segment = extractSegment(request);
    const overrides = await parseOverrideCookie(request, env);
    const resolvedFlags = await resolveFlags(env, userId, segment, overrides);

    if (Object.keys(resolvedFlags).length === 0) return originResponse;

    return applyFlagsViaRewriter(originResponse, resolvedFlags);
  },
};

// ---- Flag resolution ----

async function resolveFlags(
  env: Env,
  userId: string,
  segment: string,
  overrides: Record<string, string>
): Promise<ResolvedFlags> {
  // List all flag keys (in production, cache this list)
  const list = await env.FLAGS.list();
  const resolved: ResolvedFlags = {};

  await Promise.all(
    list.keys.map(async ({ name: flagName }) => {
      const raw = await env.FLAGS.get(flagName);
      if (!raw) return;

      const definition = JSON.parse(raw) as FlagDefinition;
      if (!definition.enabled) return; // global kill switch

      // Segment filter
      if (definition.segments.length > 0 && !definition.segments.includes(segment)) return;

      // Percentage rollout: consistent hash of userId + flagName
      const rolloutBucket = await stableHashPercent(`${userId}:${flagName}`);
      if (rolloutBucket >= definition.rolloutPercent) return;

      // Variant selection
      let variantName: string;
      if (overrides[flagName]) {
        variantName = overrides[flagName];
      } else {
        variantName = await selectVariant(definition, userId);
      }

      if (!definition.variants[variantName]) return;

      resolved[flagName] = { variant: variantName, definition };
    })
  );

  return resolved;
}

async function stableHashPercent(input: string): Promise<number> {
  const data = new TextEncoder().encode(input);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  // Take the first 4 bytes as a uint32 and mod by 100
  const view = new DataView(hashBuffer);
  const uint32 = view.getUint32(0, false);
  return uint32 % 100;
}

async function selectVariant(definition: FlagDefinition, userId: string): Promise<string> {
  const variants = Object.entries(definition.variants);
  if (variants.length === 0) return definition.defaultVariant;

  const totalWeight = variants.reduce((sum, [, v]) => sum + v.weight, 0);
  const bucket = await stableHashPercent(`${userId}:${definition.name}:variant`);
  const scaled = (bucket / 100) * totalWeight;

  let cumulative = 0;
  for (const [name, variant] of variants) {
    cumulative += variant.weight;
    if (scaled < cumulative) return name;
  }

  return definition.defaultVariant;
}

// ---- HTMLRewriter application ----

function applyFlagsViaRewriter(
  response: Response,
  flags: ResolvedFlags
): Response {
  let rewriter = new HTMLRewriter();

  // Inject flag metadata as a data attribute on <html> for client-side debugging
  rewriter = rewriter.on('html', {
    element(el) {
      const summary = Object.entries(flags)
        .map(([k, v]) => `${k}:${v.variant}`)
        .join(',');
      el.setAttribute('data-flags', summary);
    },
  });

  for (const [flagName, { variant, definition }] of Object.entries(flags)) {
    const variantDef = definition.variants[variant];

    // Apply injections
    for (const spec of variantDef.inject ?? []) {
      rewriter = rewriter.on(spec.selector, {
        element(el) {
          switch (spec.position) {
            case 'prepend':  el.prepend(spec.html, { html: true });  break;
            case 'append':   el.append(spec.html, { html: true });   break;
            case 'before':   el.before(spec.html, { html: true });   break;
            case 'after':    el.after(spec.html, { html: true });    break;
            case 'replace':  el.replace(spec.html, { html: true });  break;
          }
        },
      });
    }

    // Apply removals
    for (const selector of variantDef.remove ?? []) {
      rewriter = rewriter.on(selector, {
        element(el) {
          el.remove();
        },
      });
    }
  }

  return rewriter.transform(response);
}

// ---- User / segment extraction ----

function extractUserId(request: Request): string {
  // Try session cookie first
  const cookies = parseCookies(request.headers.get('Cookie') ?? '');
  if (cookies['session_id']) return cookies['session_id'];

  // Fall back to a stable anonymous ID based on IP + UA (privacy: no storage)
  const ip = request.headers.get('CF-Connecting-IP') ?? 'unknown';
  const ua = request.headers.get('User-Agent') ?? '';
  return `anon:${ip}:${ua.slice(0, 32)}`;
}

function extractSegment(request: Request): string {
  // Example: segment from Cloudflare country header
  const country = request.headers.get('CF-IPCountry') ?? 'XX';
  const cookies = parseCookies(request.headers.get('Cookie') ?? '');
  const plan = cookies['user_plan'] ?? 'free';
  return `${plan}:${country}`;
}

// ---- Override cookie ----
// Cookie value: base64url(JSON({ flags: Record<string,string> })):hmac

async function setOverrideCookie(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const flags: Record<string, string> = {};

  for (const [key, value] of url.searchParams) {
    if (key.startsWith('flag_')) {
      flags[key.replace('flag_', '')] = value;
    }
  }

  const payload = btoa(JSON.stringify({ flags })).replace(/=/g, '');
  const sig = await signPayload(payload, env.FLAG_SIGNING_SECRET);
  const cookieValue = `${payload}.${sig}`;

  return new Response(JSON.stringify({ ok: true, flags }), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'Set-Cookie': `flag_override=${cookieValue}; Path=/; HttpOnly; SameSite=Strict; Max-Age=86400`,
    },
  });
}

function clearOverrideCookie(): Response {
  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'Set-Cookie': 'flag_override=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0',
    },
  });
}

async function parseOverrideCookie(
  request: Request,
  env: Env
): Promise<Record<string, string>> {
  const cookies = parseCookies(request.headers.get('Cookie') ?? '');
  const raw = cookies['flag_override'];
  if (!raw) return {};

  const [payload, sig] = raw.split('.');
  if (!payload || !sig) return {};

  const valid = await verifyPayload(payload, sig, env.FLAG_SIGNING_SECRET);
  if (!valid) return {};

  try {
    const decoded = JSON.parse(atob(payload)) as { flags: Record<string, string> };
    return decoded.flags ?? {};
  } catch {
    return {};
  }
}

// ---- Crypto helpers ----

async function signPayload(payload: string, secret: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(payload));
  return btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

async function verifyPayload(payload: string, sig: string, secret: string): Promise<boolean> {
  const expected = await signPayload(payload, secret);
  return expected === sig;
}

// ---- Cookie parser ----

function parseCookies(header: string): Record<string, string> {
  return Object.fromEntries(
    header.split(';').map(c => c.trim().split('=')).filter(p => p.length >= 2)
      .map(([k, ...v]) => [k.trim(), v.join('=').trim()])
  );
}
```

```json
// Example flag definition stored in KV as key "new-checkout-flow"
{
  "name": "new-checkout-flow",
  "enabled": true,
  "rolloutPercent": 50,
  "segments": ["pro:US", "pro:GB", "free:US"],
  "variants": {
    "control": {
      "name": "Control",
      "weight": 1,
      "remove": []
    },
    "treatment": {
      "name": "New checkout",
      "weight": 1,
      "inject": [
        {
          "selector": "#checkout-cta",
          "position": "replace",
          "html": "<button id=\"checkout-cta\" class=\"btn-primary btn-lg\">Try new checkout &rarr;</button>"
        }
      ],
      "remove": ["#legacy-checkout-banner"]
    }
  },
  "defaultVariant": "control"
}
```

## Implementation Details

**KV as flag store.** Each flag is one KV key. `FLAGS.list()` returns all keys; in production with >100 flags, paginate with `list({ limit: 100, cursor })` or store a flag manifest key (`__index`) that lists active flag names to avoid listing overhead.

**Consistent hashing for rollout.** `SHA-256(userId:flagName) % 100` maps each user deterministically to a bucket 0–99. A flag with `rolloutPercent: 50` is enabled for users in buckets 0–49. Increasing `rolloutPercent` from 50 to 75 adds buckets 50–74 — users already in 0–49 remain unaffected.

**Variant selection.** Weighted random selection uses the same stable hash approach with a different salt (`:variant`), so rollout and variant assignment are independent. A 50/50 A/B test uses equal weights; a 90/10 canary uses weights `[9, 1]`.

**`data-flags` attribute on `<html>`.** Injecting the resolved flag state as a data attribute allows client-side analytics and debugging tools to read the current experiment state without an extra API call: `document.documentElement.dataset.flags`.

**HTMLRewriter chaining.** You can call `.on()` multiple times on the same `HTMLRewriter` instance, registering multiple handlers for the same or different selectors. They execute in registration order for the same selector.

## Anti-patterns

- **Evaluating flags client-side from a JS bundle** — causes flash of wrong variant and exposes flag logic to users.
- **Storing flags as a single large JSON blob in one KV key** — a single large key that changes frequently will hit KV write limits and cause cache invalidation latency. One key per flag allows targeted updates.
- **Using `Math.random()` for rollout** — non-deterministic; the same user sees different variants on each page load. Always use a stable hash of the user ID.
- **Not signing override cookies** — an unsigned cookie allows any user to override any flag, defeating the purpose of controlled rollouts.

## Gotchas

- **KV eventual consistency.** After updating a flag definition in KV, it may take up to 60 seconds to propagate to all edge nodes. Plan flag changes accordingly; use the kill switch (`enabled: false`) for instant disablement.
- **HTMLRewriter selector limitations.** The rewriter supports a subset of CSS selectors — no `:has()`, `:nth-child()`, or attribute substring matching (`[class*=...]`). Use specific IDs and class names in `InjectionSpec.selector`.
- **Concurrent handler registration in a loop.** The `for...of` loop reassigns `rewriter` to a new `HTMLRewriter` on each `.on()` call. This is correct because `HTMLRewriter.on()` returns the same instance (it is mutable). The variable reassignment is defensive but not strictly necessary — the chain is the same object.
- **Response body can only be consumed once.** Do not call `response.text()` or `response.json()` before passing the response to `rewriter.transform()` — the body stream will be exhausted. Work only with the transformed response's body.

## Verification

```bash
# Store a test flag in KV
npx wrangler kv key put --namespace-id=<NS_ID> new-checkout-flow '{
  "name":"new-checkout-flow","enabled":true,"rolloutPercent":100,
  "segments":[],"variants":{"control":{"name":"Control","weight":1,"remove":[]},
  "treatment":{"name":"Treatment","weight":1,"inject":[{"selector":"body",
  "position":"prepend","html":"<div id=test-banner>FLAG ACTIVE</div>"}],"remove":[]}},
  "defaultVariant":"control"
}'

# Run dev server
npx wrangler dev

# Test with override cookie
curl 'http://localhost:8787/__flags/override?flag_new-checkout-flow=treatment'
# Returns Set-Cookie header with signed override

# Fetch main page with the cookie and check for banner
curl http://localhost:8787/ -b 'flag_override=<cookie-value-from-above>' | \
  grep 'test-banner'
# Expected: <div id=test-banner>FLAG ACTIVE</div>

# Verify data-flags attribute
curl http://localhost:8787/ | grep -o 'data-flags="[^"]*"'
# Expected: data-flags="new-checkout-flow:treatment"
```

## Related

- `documentation/docs/policies/frontend/workers-server-sent-events-stream.md` — push real-time flag change notifications to connected clients
- `documentation/docs/policies/frontend/workers-a11y-header-injection.md` — combine a11y and feature-flag rewriting in a single HTMLRewriter chain
- `documentation/docs/policies/frontend/html-minification-htmlrewriter.md` — another HTMLRewriter pattern to compose with this one
- Cloudflare KV docs — eventual consistency guarantees and TTL-based expiry

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- https://developers.cloudflare.com/kv/
- https://martinfowler.com/articles/feature-toggles.html
- https://en.wikipedia.org/wiki/Feature_toggle

# Client-Side Feature Flags with Cloudflare Workers KV Edge Config

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-Case

You need to ship features to a subset of users—beta testers, paid tiers, geographic regions—without redeploying the frontend. A/B tests must survive page refreshes. Toggling a flag should take effect within seconds, not hours. Environment variables baked at build time are too slow; a full config service adds latency. The answer is to deliver flag state at the edge, evaluate it in your Worker, and hydrate the React tree before the first byte of HTML is sent.

---

## Context

Cloudflare Workers KV is a globally-replicated key-value store with reads that resolve from the nearest PoP, typically < 5 ms. Because KV is eventually consistent with a ~60-second propagation window, it is ideal for feature flags where near-real-time is good enough. The pattern:

1. A Cloudflare Worker sits in front of your Pages app (or is the Pages Function itself).
2. On each request the Worker reads a `flags` key from KV and injects the resolved flag set into the HTML response as a `<script>` block.
3. The React app reads that bootstrap from `window.__FLAGS__` synchronously—zero extra round trips.
4. Optionally, a thin client hook re-validates flags in the background on a short TTL so long-running sessions pick up changes.

This keeps the feature-flag path entirely out of the client bundle (no SDK weight) while letting product managers flip toggles in a Workers dashboard or CLI.

---

## 1. KV Namespace and Flag Schema

Create a namespace and store flags as a single JSON blob per environment:

```bash
# Create the namespace
wrangler kv namespace create "FEATURE_FLAGS"
# Outputs: id = "abc123..."

# Store initial flag config
wrangler kv key put --namespace-id=abc123 flags '{
  "new_checkout": false,
  "beta_dashboard": true,
  "ai_recommendations": {"enabled": true, "rollout": 0.2}
}' --remote
```

TypeScript schema for flag values:

```typescript
// types/flags.ts
export type FlagValue = boolean | { enabled: boolean; rollout: number };

export interface FeatureFlags {
  new_checkout: boolean;
  beta_dashboard: boolean;
  ai_recommendations: FlagValue;
 // allow future flags without type changes
}

export const DEFAULT_FLAGS: FeatureFlags = {
  new_checkout: false,
  beta_dashboard: false,
  ai_recommendations: false,
};
```

---

## 2. Worker / Pages Function: Resolving Flags at the Edge

```typescript
// functions/_middleware.ts  (Cloudflare Pages Functions)
import type { FeatureFlags } from '../types/flags';

interface Env {
  FEATURE_FLAGS: KVNamespace;
}

export const onRequest: PagesFunction<Env> = async (context) => {
  const { request, env, next } = context;

  // 1. Fetch flags from KV (cacheTtl=60 avoids hammering the store)
  const raw = await env.FEATURE_FLAGS.get('flags', {
    type: 'json',
    cacheTtl: 60,
  });
  const flags: FeatureFlags = raw ?? DEFAULT_FLAGS;

  // 2. Evaluate per-user overrides (cookie, header, query param)
  const resolved = resolveFlags(flags, request);

  // 3. Fetch the underlying HTML from Pages
  const response = await next();

  // 4. Only inject into HTML responses
  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.includes('text/html')) return response;

  // 5. Inject flags bootstrap before </head>
  const flagScript = `<script>window.__FLAGS__=${JSON.stringify(resolved)}</script>`;
  return new HTMLRewriter()
    .on('head', {
      element(el) {
        el.append(flagScript, { html: true });
      },
    })
    .transform(response);
};

function resolveFlags(base: FeatureFlags, request: Request): FeatureFlags {
  const url = new URL(request.url);
  const overrideCookie = parseCookieOverride(request.headers.get('cookie'));
  const forcedFlag = url.searchParams.get('__flag');
  const forcedValue = url.searchParams.get('__val');

  const resolved = { ...base };

  // QA override: ?__flag=new_checkout&__val=true
  if (forcedFlag && forcedValue !== null && forcedFlag in resolved) {
    resolved[forcedFlag] = forcedValue === 'true';
  }

  // Cookie overrides from previous opt-in
  for (const [k, v] of Object.entries(overrideCookie)) {
    if (k in resolved) resolved[k] = v;
  }

  // Percentage rollout evaluation
  for (const [key, val] of Object.entries(resolved)) {
    if (typeof val === 'object' && 'rollout' in val) {
      const userId = getUserId(request);
      resolved[key] = val.enabled && deterministicBucket(userId, key) < val.rollout;
    }
  }

  return resolved;
}

function parseCookieOverride(cookieHeader: string | null): Record<string, boolean> {
  if (!cookieHeader) return {};
  const result: Record<string, boolean> = {};
  for (const part of cookieHeader.split(';')) {
    const [name, value] = part.trim().split('=');
    if (name?.startsWith('flag_')) {
      result[name.slice(5)] = value === 'true';
    }
  }
  return result;
}

function getUserId(request: Request): string {
  const cf = (request as any).cf;
  return cf?.clientTcpRtt?.toString() ?? request.headers.get('cf-connecting-ip') ?? 'anon';
}

function deterministicBucket(userId: string, flagKey: string): number {
  let hash = 0;
  const str = `${flagKey}:${userId}`;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash % 100) / 100;
}
```

---

## 3. React Context: Reading Bootstrap Flags

```typescript
// lib/flags/context.tsx
import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react';
import type { FeatureFlags } from '../../types/flags';

declare global {
  interface Window {
    __FLAGS__?: FeatureFlags;
  }
}

const FlagsContext = createContext<FeatureFlags | null>(null);

export function FlagsProvider({ children }: { children: ReactNode }) {
  const [flags, setFlags] = useState<FeatureFlags>(
    () => window.__FLAGS__ ?? DEFAULT_FLAGS,
  );

  // Background re-validation every 60 s so long-running sessions pick up changes
  const refresh = useCallback(async () => {
    try {
      const res = await fetch('/api/flags', { credentials: 'same-origin' });
      if (res.ok) setFlags(await res.json());
    } catch {
      // ignore; keep stale flags
    }
  }, []);

  useEffect(() => {
    const id = setInterval(refresh, 60_000);
    return () => clearInterval(id);
  }, [refresh]);

  return <FlagsContext.Provider value={flags}>{children}</FlagsContext.Provider>;
}

export function useFlags(): FeatureFlags {
  const ctx = useContext(FlagsContext);
  if (!ctx) throw new Error('useFlags must be used inside <FlagsProvider>');
  return ctx;
}

export function useFlag<K extends keyof FeatureFlags>(key: K): boolean {
  const flags = useFlags();
  const val = flags[key];
  return typeof val === 'boolean' ? val : false;
}
```

Usage in a component:

```tsx
// components/Checkout.tsx
import { useFlag } from '../lib/flags/context';

export function CheckoutButton() {
  const newCheckout = useFlag('new_checkout');

  return newCheckout ? (
    <NewCheckoutFlow />
  ) : (
    <LegacyCheckout />
  );
}
```

---

## 4. Flag Refresh API Route (Pages Function)

```typescript
// functions/api/flags.ts
import type { FeatureFlags } from '../../types/flags';

interface Env {
  FEATURE_FLAGS: KVNamespace;
}

export const onRequestGet: PagesFunction<Env> = async ({ env, request }) => {
  const raw = await env.FEATURE_FLAGS.get('flags', { type: 'json', cacheTtl: 30 });
  const flags: FeatureFlags = resolveFlags(raw ?? DEFAULT_FLAGS, request);

  return new Response(JSON.stringify(flags), {
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'private, max-age=30',
    },
  });
};
```

---

## 5. Admin CLI: Updating Flags Without Redeployment

```bash
# Flip a flag immediately (takes effect within ~60 s globally)
wrangler kv key put --namespace-id=abc123 flags "$(
  wrangler kv key get --namespace-id=abc123 flags \
  | jq '.new_checkout = true'
)" --remote

# Gradual rollout to 10% of users
wrangler kv key put --namespace-id=abc123 flags "$(
  wrangler kv key get --namespace-id=abc123 flags \
  | jq '.ai_recommendations = {enabled: true, rollout: 0.1}'
)" --remote

# Verify current state
wrangler kv key get --namespace-id=abc123 flags --remote | jq .
```

---

## 6. Testing Flag Variants

```typescript
// __tests__/Checkout.test.tsx
import { render, screen } from '@testing-library/react';
import { FlagsContext } from '../lib/flags/context';
import { CheckoutButton } from '../components/Checkout';
import type { FeatureFlags } from '../types/flags';

function renderWithFlags(flags: Partial<FeatureFlags>) {
  const merged: FeatureFlags = { ...DEFAULT_FLAGS, ...flags };
  return render(
    <FlagsContext.Provider value={merged}>
      <CheckoutButton />
    </FlagsContext.Provider>,
  );
}

test('shows new checkout when flag is on', () => {
  renderWithFlags({ new_checkout: true });
  expect(screen.getByTestId('new-checkout-flow')).toBeInTheDocument();
});

test('shows legacy checkout when flag is off', () => {
  renderWithFlags({ new_checkout: false });
  expect(screen.getByTestId('legacy-checkout')).toBeInTheDocument();
});
```

---

## Anti-Patterns

- **Fetching flags client-side on mount** — causes layout shift and flash of wrong variant. Always bootstrap from `window.__FLAGS__` injected by the Worker.
- **One KV key per flag** — adds KV reads per request proportional to flag count. Keep all flags in one JSON blob; a single `get` is one billable KV read regardless of payload size.
- **Evaluating percentage rollouts by Math.random()** — produces different buckets on each render/refresh, causing users to flicker between variants. Use a deterministic hash of a stable user identifier.
- **Shipping the flag SDK in the bundle** — SDKs like LaunchDarkly's JS client add 50–100 kB. The edge-injection pattern eliminates client-side SDK weight entirely.
- **Storing secrets in the same KV namespace as flags** — KV values injected into HTML are world-readable. Use Workers Secrets / environment variables for anything sensitive.

---

## Gotchas

- **KV eventual consistency**: After `wrangler kv key put`, expect up to 60 seconds before all PoPs serve the new value. Build operational runbooks around this; do not use KV flags for anything requiring sub-second cutover.
- **HTMLRewriter streaming**: `HTMLRewriter.transform()` streams the response body. Do not buffer the entire response before injecting; the callback approach shown above is correct and keeps TTFB low.
- **SSR hydration mismatch**: If your RSC layer also reads `window.__FLAGS__`, ensure the server-rendered HTML and the client hydration see identical flag values. The Worker injection guarantees this because the same resolved object is both embedded in the HTML and available to client code before React hydrates.
- **QA override security**: The `?__flag=` query-param override should be disabled in production or gated behind an internal IP check / signed HMAC to prevent users from enabling unreleased flags.
- **Cache-Control interaction**: Pages CDN may cache your HTML. Set `Cache-Control: private` or use `Vary: Cookie` when flags differ by user to prevent cached flag-off responses from serving flag-on users.

---

## Verification

```bash
# 1. Confirm flags are injected in the HTML
curl -s https://your-app.pages.dev/ | grep '__FLAGS__'

# 2. Toggle a flag and verify propagation within 60 s
wrangler kv key put --namespace-id=abc123 flags '{"new_checkout":true,...}' --remote
sleep 65
curl -s https://your-app.pages.dev/ | grep -o '"new_checkout":true'

# 3. Test QA override
curl -s "https://your-app.pages.dev/?__flag=beta_dashboard&__val=true" \
  | grep '"beta_dashboard":true'

# 4. Refresh endpoint returns fresh flags
curl -s https://your-app.pages.dev/api/flags | jq .
```

---

## Related

- `react-query-cache-invalidation-workers-api-versioning.md`
- `cloudflare-pages-headers-csp-mobile.md`
- `build-time-env-baking-chunk-hash.md`
- `nextjs-middleware-patterns.md`

---

## Sources

- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
- HTMLRewriter API — https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- Cloudflare Pages Functions — https://developers.cloudflare.com/pages/functions/

# Micro-Frontend Integration with Module Federation

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Multiple product teams deliver independent React/Vue/Svelte applications that need to compose into
a single user-facing shell. Teams deploy on their own cadences; a change to the checkout app must
not require a full rebuild of the navigation shell. You need runtime composition — not build-time
monorepo bundling — so each remote can be updated independently and the host picks up the new
version without re-deploying itself.

Classic SPA mono-bundling collapses this independence: every team must synchronize releases, share
the exact same dependency versions, and tolerate multi-minute CI pipelines that touch the whole
product. Module Federation (Webpack 5 / Rspack / Vite) solves the build side; Cloudflare Workers
and Pages solve the edge delivery side so remotes are served with zero-latency from the PoP nearest
to each user.

---

## Context

Module Federation lets a **host** application dynamically import **remote** bundles at runtime.
Each remote exposes components or utilities through a `remoteEntry.js` manifest. The host fetches
that manifest, resolves shared dependencies (React, ReactDOM) from a singleton scope, and mounts
the remote component inside its own React tree.

At the network layer the remotes are just static JavaScript bundles. Cloudflare Pages or a Worker
serving R2 objects provides:

- Global CDN caching with fine-grained `Cache-Control`
- Cache purge per-remote on deployment (via the Cloudflare API)
- Edge-side `remoteEntry.js` rewriting to inject per-environment URLs
- A/B testing by varying which `remoteEntry.js` URL a user receives

The shell Worker acts as the composition layer: it renders the initial HTML, injects the correct
remote URLs per user segment or environment, and the browser takes over for client-side federation.

---

## 1. Host Shell Configuration (Webpack 5)

```javascript
// webpack.config.js — host shell
const { ModuleFederationPlugin } = require('webpack').container;

module.exports = {
  plugins: [
    new ModuleFederationPlugin({
      name: 'shell',
      remotes: {
        // URL injected at runtime via __webpack_public_path__ trick
        checkout: 'checkout@[checkoutUrl]/remoteEntry.js',
        navigation: 'navigation@[navUrl]/remoteEntry.js',
      },
      shared: {
        react: { singleton: true, requiredVersion: '^18.3.0' },
        'react-dom': { singleton: true, requiredVersion: '^18.3.0' },
        'react-router-dom': { singleton: true, requiredVersion: '^6.0.0' },
      },
    }),
  ],
};
```

The `[checkoutUrl]` placeholder is replaced by the shell Worker before serving the HTML.
This means the host bundle itself never hard-codes remote origins — the Worker controls routing
per-environment.

---

## 2. Cloudflare Worker as Shell Composer

The shell Worker fetches the host HTML from R2 (or Pages), replaces remote URL tokens, and
streams the result to the client.

```typescript
// shell-worker/src/index.ts
export interface Env {
  SHELL_BUCKET: R2Bucket;
  REMOTE_REGISTRY: KVNamespace; // maps remoteName -> { url, version }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Serve remoteEntry requests directly (cache-first from R2)
    if (url.pathname.startsWith('/remotes/')) {
      return serveRemoteAsset(request, env);
    }

    // Serve shell HTML with injected remote URLs
    const shellObj = await env.SHELL_BUCKET.get('index.html');
    if (!shellObj) return new Response('Not Found', { status: 404 });

    const remoteRegistry = await resolveRemotes(env);
    const html = await shellObj.text();
    const composed = injectRemoteUrls(html, remoteRegistry);

    return new Response(composed, {
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'no-store', // shell is dynamic; remotes are cached
      },
    });
  },
};

async function resolveRemotes(
  env: Env
): Promise<Record<string, { url: string; version: string }>> {
  const [checkout, navigation] = await Promise.all([
    env.REMOTE_REGISTRY.get('checkout', 'json'),
    env.REMOTE_REGISTRY.get('navigation', 'json'),
  ]);
  return { checkout, navigation } as Record<string, { url: string; version: string }>;
}

function injectRemoteUrls(
  html: string,
  registry: Record<string, { url: string; version: string }>
): string {
  return html
    .replace('[checkoutUrl]', registry.checkout?.url ?? '')
    .replace('[navUrl]', registry.navigation?.url ?? '');
}

async function serveRemoteAsset(request: Request, env: Env): Promise<Response> {
  const key = new URL(request.url).pathname.slice(1); // strip leading /
  const obj = await env.SHELL_BUCKET.get(key, {
    onlyIf: request.headers,
    range: request.headers,
  });
  if (!obj) return new Response('Not Found', { status: 404 });

  return new Response(obj.body, {
    headers: {
      'Content-Type': 'application/javascript',
      // Remotes are content-addressed; cache aggressively
      'Cache-Control': 'public, max-age=31536000, immutable',
      ETag: obj.httpEtag,
    },
  });
}
```

---

## 3. Remote Deployment and Registry Update

Each remote team owns a Pages project or Worker. On successful deployment they write their new URL
into the shared KV registry using the Cloudflare API — no shell re-deploy needed.

```bash
#!/usr/bin/env bash
# deploy-remote.sh  (runs in checkout team's CI)
set -euo pipefail

REMOTE_NAME="checkout"
ACCOUNT_ID="${CF_ACCOUNT_ID}"
KV_NAMESPACE_ID="${REMOTE_REGISTRY_KV_ID}"
API_TOKEN="${CF_API_TOKEN}"

# 1. Upload new bundle to R2 / Pages (handled separately)
BUNDLE_URL="https://assets.example.com/remotes/checkout/${GIT_SHA}/remoteEntry.js"

# 2. Write new entry to shared KV registry
curl -sf -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/storage/kv/namespaces/${KV_NAMESPACE_ID}/values/${REMOTE_NAME}" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"${BUNDLE_URL}\", \"version\": \"${GIT_SHA}\"}"

echo "Registry updated: ${REMOTE_NAME} -> ${BUNDLE_URL}"
```

The shell Worker reads this KV on every request (with a short TTL edge cache) and injects the
latest remote URL. Zero shell redeployment needed.

---

## 4. Shared Dependency Singleton Enforcement

The biggest runtime error in Module Federation is duplicate React instances. Two remotes that
each bundle their own React will produce hook errors and broken context. Enforce singleton
resolution by auditing the shared scope in the browser:

```typescript
// debug-shared-scope.ts  (run in browser console during development)
declare const __webpack_share_scopes__: Record<
  string,
  Record<string, Record<string, { loaded?: number; get: () => Promise<unknown> }>>
>;

function auditSharedScope(): void {
  const scope = __webpack_share_scopes__?.default;
  if (!scope) {
    console.warn('No shared scope found — are you running a federated app?');
    return;
  }

  for (const [pkg, versions] of Object.entries(scope)) {
    const versionKeys = Object.keys(versions);
    if (versionKeys.length > 1) {
      console.error(
        `[MF] Duplicate shared package "${pkg}": ${versionKeys.join(', ')}`
      );
    } else {
      console.log(`[MF] ✓ ${pkg} @ ${versionKeys[0]}`);
    }
  }
}

auditSharedScope();
```

In production, instrument this as a startup check and emit a `console.error` (or send to
Analytics Engine) if any singleton package resolves to more than one version.

---

## Anti-patterns

- **Hard-coding remote URLs in the host bundle.** If the remote URL changes, you must rebuild and
  redeploy the host. Use runtime injection via the shell Worker (section 2).
- **Sharing too many modules.** Marking every utility library as `shared` bloats the shared scope
  and causes version negotiation failures. Only `react`, `react-dom`, and routing libraries should
  be singletons; everything else is fetched by each remote independently.
- **Blocking the shell render on remote load.** Always wrap remote components in `<Suspense>` with
  a meaningful fallback. A slow or failing remote must never block the entire page.
- **Deploying remotes without cache busting.** `remoteEntry.js` at a stable URL cached at the edge
  means users get stale code. Name remotes with content hashes or commit SHAs and set
  `immutable` cache headers.
- **Ignoring Content-Security-Policy.** Module Federation fetches and executes third-party JS.
  CSP `script-src` must explicitly allow remote origins or use `'strict-dynamic'` with nonces.

---

## Gotchas

- **KV read latency in the critical path.** If the shell Worker reads KV on every request without
  caching, cold reads add ~20 ms per key. Use `{ cacheTtl: 60 }` on KV reads or cache the
  resolved registry in the Worker's in-memory module scope for the lifetime of the isolate.
- **Rspack vs Webpack 5 compatibility.** Rspack's Module Federation implementation is largely
  compatible but diverges on `exposes` path resolution for CJS modules. Test interop explicitly.
- **SSR with Module Federation.** Server-side rendering requires `@module-federation/node` or a
  custom resolver. The shell Worker must import remote modules on the server side too; this
  doubles the complexity and is usually deferred to client-only federation.
- **React version mismatch between remotes.** Even with `singleton: true`, if two remotes declare
  incompatible `requiredVersion` ranges, Module Federation will log a warning and load separate
  instances. Pin React to an exact version across all remote `package.json` files.

---

## Verification

```bash
# 1. Confirm remoteEntry.js is served with correct cache headers
curl -sI https://assets.example.com/remotes/checkout/abc123/remoteEntry.js \
  | grep -E 'cache-control|etag|content-type'

# 2. Confirm shell HTML injects correct remote URL
curl -s https://shell.example.com/ \
  | grep -o 'checkout@[^"]*remoteEntry.js'

# 3. Check KV registry value
wrangler kv key get --namespace-id=<NS_ID> checkout

# 4. Audit for duplicate React in the browser (paste in DevTools console)
Object.keys(__webpack_share_scopes__?.default ?? {}).forEach(pkg => {
  const v = Object.keys(__webpack_share_scopes__.default[pkg]);
  if (v.length > 1) console.error('DUPLICATE:', pkg, v);
});
```

---

## Related

- `caching-layers-cloudflare-workers-kv-r2.md`
- `feature-flag-cloudflare-workers-kv.md`
- `a-b-testing-architecture.md`
- `edge-first-architecture-patterns.md`
- `api-gateway-pattern-cloudflare-workers.md`

---

## Sources

- Webpack Module Federation documentation: https://webpack.js.org/concepts/module-federation/
- Module Federation examples repository: https://github.com/module-federation/module-federation-examples
- Cloudflare Workers KV documentation: https://developers.cloudflare.com/kv/
- Cloudflare R2 object storage: https://developers.cloudflare.com/r2/
- "Micro Frontends" by Cam Jackson (martinfowler.com)
- Rspack Module Federation guide: https://rspack.dev/guide/features/module-federation

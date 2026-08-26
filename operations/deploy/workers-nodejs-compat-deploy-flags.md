# Workers Node.js Compat Deploy Flags

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You are migrating a Node.js application to Cloudflare Workers and it uses standard
library modules (`crypto`, `buffer`, `stream`, `path`, `url`, `events`, `util`,
`assert`, `process`). Without explicit configuration the Worker throws at runtime:
`Cannot find module 'node:crypto'`. Alternatively your third-party dependency (e.g.
`jsonwebtoken`, `pg`, `ioredis`, `zod`) pulls in a Node built-in and the Worker fails
even though you never wrote `import crypto` yourself.

This article covers how to select, pin, and deploy the correct `nodejs_compat` or
`nodejs_compat_v2` flag, how to audit which built-ins your bundle actually imports, and
how to promote the flag safely across environments.

## Context

Cloudflare's workerd runtime is not Node.js. It implements the WinterCG subset of Web
APIs. Node.js built-ins are opt-in via `compatibility_flags` in `wrangler.toml`.

Two flags exist (mutually exclusive):
- **`nodejs_compat`** — legacy polyfill mode; uses `unenv` to shim most Node built-ins
  as JavaScript implementations, with some gaps.
- **`nodejs_compat_v2`** — native implementation mode (workerd 2024+); provides
  real `node:*` module support where the workerd runtime implements them natively.
  Requires `compatibility_date >= "2024-09-23"`.

`nodejs_compat_v2` is the current recommended flag. `nodejs_compat` remains available
for backward compatibility.

---

## Enabling Node.js Compat in wrangler.toml

```toml
# wrangler.toml
name                = "my-worker"
main                = "src/index.ts"
compatibility_date  = "2024-09-23"          # minimum for nodejs_compat_v2
compatibility_flags = ["nodejs_compat_v2"]  # ← recommended

# Per-environment override (staging still on v1 during migration)
[env.staging]
compatibility_date  = "2024-09-23"
compatibility_flags = ["nodejs_compat_v2"]

[env.production]
compatibility_date  = "2024-09-23"
compatibility_flags = ["nodejs_compat_v2"]
```

For projects that cannot yet move to `nodejs_compat_v2`:

```toml
compatibility_date  = "2023-01-01"
compatibility_flags = ["nodejs_compat"]
```

**Do not set both flags** — they conflict and Wrangler will error.

---

## Which Node.js Modules Are Supported

### Natively supported with nodejs_compat_v2 (as of 2026-08)

```
node:assert           node:assert/strict
node:async_hooks      node:buffer
node:crypto           node:dgram (partial)
node:dns              node:dns/promises
node:events           node:fs (non-streaming read only)
node:http             node:https
node:net              node:os (partial)
node:path             node:path/posix  node:path/win32
node:process          node:querystring
node:readline         node:stream
node:stream/promises  node:string_decoder
node:timers           node:timers/promises
node:tls (partial)    node:url
node:util             node:util/types
node:zlib
```

### Not available (even with compat flags)

```
node:child_process    node:cluster
node:domain           node:fs (write / watch / directory ops)
node:http2 (server)   node:inspector
node:perf_hooks       node:repl
node:v8               node:vm
node:worker_threads
```

---

## Auditing Built-in Usage in Your Bundle

Before enabling the flag in production, confirm which built-ins your bundle actually
imports. A false positive (enabling the flag when it isn't needed) costs nothing in
performance but introduces a wider compatibility surface for future flag changes.

```bash
# Build the bundle then grep for node: imports
npx wrangler deploy --dry-run --outdir /tmp/worker-build/
grep -E "require\(['\"]node:" /tmp/worker-build/*.js | sort -u
grep -E 'from ["\']node:' /tmp/worker-build/*.js | sort -u
```

Automated CI check:

```typescript
// scripts/audit-node-imports.ts
import { execSync } from "child_process";
import { readFileSync, readdirSync } from "fs";
import { join } from "path";

const ALLOWED_MODULES = new Set([
  "node:crypto", "node:buffer", "node:stream", "node:path",
  "node:url", "node:events", "node:util", "node:assert",
  "node:http", "node:https", "node:timers", "node:os",
  "node:zlib", "node:dns", "node:net",
]);

const FORBIDDEN_MODULES = new Set([
  "node:child_process", "node:vm", "node:worker_threads",
  "node:v8", "node:cluster", "node:fs",
]);

execSync("npx wrangler deploy --dry-run --outdir /tmp/worker-build", {
  stdio: "inherit",
});

const bundleDir = "/tmp/worker-build";
const files = readdirSync(bundleDir).filter((f) => f.endsWith(".js"));

const violations: string[] = [];
for (const file of files) {
  const content = readFileSync(join(bundleDir, file), "utf8");
  const matches = content.match(/["']node:[a-z_/]+["']/g) ?? [];
  for (const m of matches) {
    const mod = m.replace(/['"]/g, "");
    if (FORBIDDEN_MODULES.has(mod)) {
      violations.push(`${file}: imports unsupported ${mod}`);
    }
  }
}

if (violations.length) {
  console.error("Unsupported Node.js module imports found:\n" + violations.join("\n"));
  process.exit(1);
}
console.log(`Audit passed — ${files.length} bundle files checked`);
```

---

## Promoting the Flag Across Environments

Node.js compat flags interact with `compatibility_date` — changing either can alter
runtime behaviour. Treat them as a coupled unit and promote them together.

```bash
# Stage 1: enable on dev, run integration tests
npx wrangler deploy --env dev

# Stage 2: staging deploy + smoke test
npx wrangler deploy --env staging
curl -sf https://my-worker-staging.example.workers.dev/health | jq -e '.ok'

# Stage 3: production
npx wrangler deploy   # uses wrangler.toml root section (production)
```

CI pipeline:

```yaml
# .github/workflows/deploy.yml
jobs:
  deploy:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        env: [staging, production]
      max-parallel: 1   # sequential — staging must pass before production
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - run: npm ci

      - name: Audit Node.js imports
        run: npx tsx scripts/audit-node-imports.ts

      - name: Deploy ${{ matrix.env }}
        run: |
          if [[ "${{ matrix.env }}" == "production" ]]; then
            npx wrangler deploy
          else
            npx wrangler deploy --env ${{ matrix.env }}
          fi
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Smoke test ${{ matrix.env }}
        run: |
          URL=$(
            [[ "${{ matrix.env }}" == "production" ]] \
              && echo "${{ vars.PROD_URL }}" \
              || echo "${{ vars.STAGING_URL }}"
          )
          curl -sf "$URL/health" | jq -e '.ok == true'
```

---

## Using Node.js Crypto (Common Use-case)

```typescript
// src/auth/jwt.ts — using node:crypto with nodejs_compat_v2
import { createHmac, timingSafeEqual } from "node:crypto";

export function signPayload(payload: string, secret: string): string {
  return createHmac("sha256", secret).update(payload).digest("hex");
}

export function verifySignature(
  payload: string,
  signature: string,
  secret: string
): boolean {
  const expected = Buffer.from(signPayload(payload, secret), "hex");
  const provided = Buffer.from(signature, "hex");
  if (expected.length !== provided.length) return false;
  return timingSafeEqual(expected, provided);
}
```

Equivalent using the Web Crypto API (no compat flag needed):

```typescript
// src/auth/jwt-webcrypto.ts — no compat flag required
const encoder = new TextEncoder();

export async function signPayload(payload: string, secret: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, encoder.encode(payload));
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
```

Prefer Web Crypto for new code; use `node:crypto` only when migrating existing libraries.

---

## Anti-patterns

- **Enabling `nodejs_compat` and `nodejs_compat_v2` simultaneously** — they conflict;
  Wrangler rejects the combination.
- **Setting `nodejs_compat_v2` with a `compatibility_date` older than 2024-09-23** —
  the flag will silently fall back to v1 behaviour or fail, depending on Wrangler
  version.
- **Assuming `node:fs` write operations work** — they don't; `node:fs` in workerd
  supports read-only access to bundled files only. Use R2 for runtime file writes.
- **Using `node:worker_threads`** — not supported; run parallel work via Durable Objects
  or multiple Workers connected via Service Bindings.

## Gotchas

- Enabling `nodejs_compat_v2` changes the semantics of how `node:stream` Readable/
  Writable streams interact with `Response`/`Request` bodies. Test streaming pipelines
  explicitly after upgrading from `nodejs_compat`.
- The `process.env` object in workerd with `nodejs_compat_v2` is read-only and empty —
  environment variables are accessed via `env.*` bindings, not `process.env`.
- `Buffer` is globally available with either compat flag without an explicit import,
  but relying on the implicit global is fragile; import it explicitly.
- Some npm packages conditionally `require('node:X')` based on runtime detection (e.g.
  checking `typeof process !== 'undefined'`). The compat flag makes this check pass,
  which may load code paths that still use unsupported APIs. Audit carefully.

## Verification

```bash
# Verify the compat flag is applied to the deployed worker
wrangler deployments list --name my-worker | head -3

# Inspect compatibility settings of the latest deployment
wrangler deployments view --name my-worker | grep -A5 "compatibility"

# Runtime test: exercise a node:crypto code path
curl -sf https://my-worker.example.workers.dev/api/sign \
  -H "Content-Type: application/json" \
  -d '{"payload":"hello"}' | jq .
```

## Related

- `pages-functions-bundling-edge-cases.md`
- `workers-compatibility-date-staged-migration.md`
- `workers-bundle-analysis-regression-ci.md`
- `wrangler-config-validation-pre-deploy-ci-hook.md`
- `workers-hyperdrive-connection-pool-deploy.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/nodejs/
- https://developers.cloudflare.com/workers/configuration/compatibility-dates/
- https://developers.cloudflare.com/workers/configuration/compatibility-flags/#nodejs_compat_v2
- https://github.com/nicolo-ribaudo/tc39-proposal-nodejs-compat
- https://blog.cloudflare.com/more-npm-packages-on-cloudflare-workers-combining-polyfills-and-native-code/

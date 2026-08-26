# Automated Secrets Rotation Using Workers + KV as a Secrets Vault

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your Workers use long-lived API keys or database credentials stored as Wrangler secrets. Rotating them requires a manual `wrangler secret put` followed by a redeployment, creating downtime risk and an audit gap. You need a programmatic rotation system where secrets are versioned in KV, rotated on a schedule, and consumed by Workers without redeployment or cold-key errors during the rotation window.

## Context

Workers secrets (set via `wrangler secret put`) are baked into the Worker at deploy time and require a new deployment to update. For secrets that rotate frequently (API keys, OAuth tokens, signing keys), this is operationally expensive.

The alternative: treat KV as a lightweight secrets vault. A secret lives in KV under a versioned key. A rotation cron Worker mints new secret versions and retires old ones. Consumer Workers always fetch the current version at request time — with a short in-process cache — so rotation is transparent and zero-downtime.

This pattern does not replace Cloudflare Workers Secrets for high-sensitivity values that must never appear in KV (e.g., private keys used for signing). Use it for rotating API credentials and tokens.

## Solution

### KV key schema

```
secrets/{name}/current          -> "v3"                  (current version pointer)
secrets/{name}/versions/v3      -> { value, createdAt, expiresAt, rotatedBy }
secrets/{name}/versions/v2      -> { value, createdAt, expiresAt, rotatedBy }  (previous, still valid during grace)
secrets/{name}/audit            -> JSON array of AuditEntry (append-only log, capped)
```

### Types

```typescript
// src/vault/types.ts
export interface SecretVersion {
  value: string;
  createdAt: number;   // Unix ms
  expiresAt: number;   // Unix ms — when this version becomes invalid
  rotatedBy: string;   // "cron" | "manual" | worker name
}

export interface AuditEntry {
  event: "created" | "rotated" | "expired" | "consumed";
  version: string;
  secretName: string;
  ts: number;
  actor: string;
}

export interface Env {
  VAULT_KV: KVNamespace;
  // Injected via wrangler secret put — only for the vault Worker itself
  UPSTREAM_API_KEY_ENDPOINT: string; // URL to call to mint a new key
  VAULT_ADMIN_TOKEN: string;         // protects manual rotation endpoint
}

export const GRACE_PERIOD_MS = 5 * 60 * 1000; // 5 minutes overlap between versions
export const MAX_AUDIT_ENTRIES = 500;
```

### Vault read helper (for consumer Workers)

```typescript
// src/vault/client.ts
import type { SecretVersion } from "./types";

const IN_PROCESS_CACHE = new Map<string, { value: string; expiresAt: number }>();
const CACHE_TTL_MS = 30_000; // refresh from KV every 30 seconds

export async function getSecret(
  kv: KVNamespace,
  name: string
): Promise<string> {
  const cacheKey = `secrets/${name}`;
  const cached = IN_PROCESS_CACHE.get(cacheKey);
  if (cached && cached.expiresAt > Date.now()) {
    return cached.value;
  }

  // Read current version pointer
  const currentVersion = await kv.get(`secrets/${name}/current`);
  if (!currentVersion) {
    throw new Error(`Secret '${name}' not found in vault`);
  }

  // Read the versioned value
  const record = await kv.get<SecretVersion>(
    `secrets/${name}/versions/${currentVersion}`,
    "json"
  );
  if (!record) {
    throw new Error(`Secret '${name}' version '${currentVersion}' missing`);
  }
  if (record.expiresAt < Date.now()) {
    throw new Error(`Secret '${name}' version '${currentVersion}' is expired`);
  }

  // Cache locally
  IN_PROCESS_CACHE.set(cacheKey, {
    value: record.value,
    expiresAt: Date.now() + CACHE_TTL_MS,
  });

  return record.value;
}
```

### Secret provisioning (initial write)

```typescript
// src/vault/provision.ts
import type { Env, SecretVersion, AuditEntry } from "./types";
import { MAX_AUDIT_ENTRIES } from "./types";

export async function provisionSecret(
  kv: KVNamespace,
  name: string,
  value: string,
  ttlMs: number,
  actor: string
): Promise<string> {
  const version = `v${Date.now()}`;
  const now = Date.now();

  const record: SecretVersion = {
    value,
    createdAt: now,
    expiresAt: now + ttlMs,
    rotatedBy: actor,
  };

  await Promise.all([
    kv.put(`secrets/${name}/versions/${version}`, JSON.stringify(record), {
      // KV TTL slightly longer than logical expiry to allow grace reads
      expirationTtl: Math.ceil((ttlMs + 10 * 60 * 1000) / 1000),
    }),
    kv.put(`secrets/${name}/current`, version),
  ]);

  await appendAudit(kv, name, {
    event: "created",
    version,
    secretName: name,
    ts: now,
    actor,
  });

  return version;
}

async function appendAudit(kv: KVNamespace, name: string, entry: AuditEntry) {
  const raw = await kv.get<AuditEntry[]>(`secrets/${name}/audit`, "json");
  const log = raw ?? [];
  log.push(entry);
  // Cap audit log size
  const trimmed = log.slice(-MAX_AUDIT_ENTRIES);
  await kv.put(`secrets/${name}/audit`, JSON.stringify(trimmed));
}
```

### Rotation cron Worker

```typescript
// src/vault/rotation.ts
import type { Env, SecretVersion } from "./types";
import { GRACE_PERIOD_MS } from "./types";
import { provisionSecret } from "./provision";

/** Secret rotation config: name -> TTL and how to mint a new value */
const ROTATION_PLAN: Array<{
  name: string;
  ttlMs: number;
  mint: (env: Env) => Promise<string>;
}> = [
  {
    name: "upstream_api_key",
    ttlMs: 24 * 60 * 60 * 1000, // 24 hours
    mint: async (env) => {
      const resp = await fetch(env.UPSTREAM_API_KEY_ENDPOINT, {
        method: "POST",
        headers: { Authorization: `Bearer ${env.VAULT_ADMIN_TOKEN}` },
      });
      if (!resp.ok) throw new Error(`Mint failed: ${resp.status}`);
      const { key } = await resp.json<{ key: string }>();
      return key;
    },
  },
];

async function rotateSingle(
  env: Env,
  plan: (typeof ROTATION_PLAN)[number]
): Promise<void> {
  const { name, ttlMs, mint } = plan;
  const kv = env.VAULT_KV;

  // Fetch current version to keep it alive during grace period
  const oldVersion = await kv.get(`secrets/${name}/current`);

  // Mint new secret value
  const newValue = await mint(env);

  // Write new version (sets current pointer atomically-ish via two puts)
  const newVersion = await provisionSecret(kv, name, newValue, ttlMs, "cron");

  // Extend expiry of old version by grace period so in-flight requests finish
  if (oldVersion) {
    const oldRecord = await kv.get<SecretVersion>(
      `secrets/${name}/versions/${oldVersion}`,
      "json"
    );
    if (oldRecord) {
      const extended: SecretVersion = {
        ...oldRecord,
        expiresAt: Date.now() + GRACE_PERIOD_MS,
      };
      await kv.put(
        `secrets/${name}/versions/${oldVersion}`,
        JSON.stringify(extended),
        { expirationTtl: Math.ceil(GRACE_PERIOD_MS / 1000) + 60 }
      );
    }
  }

  console.log(`Rotated secret '${name}': ${oldVersion} -> ${newVersion}`);
}

export async function runRotation(env: Env): Promise<void> {
  await Promise.allSettled(
    ROTATION_PLAN.map((plan) => rotateSingle(env, plan))
  );
}
```

### Main Worker entry point

```typescript
// src/index.ts
import type { Env } from "./vault/types";
import { runRotation } from "./vault/rotation";

export default {
  // Cron: rotate secrets on schedule
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runRotation(env));
  },

  // HTTP: manual rotation trigger (admin only)
  async fetch(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
    if (request.method !== "POST" || new URL(request.url).pathname !== "/rotate") {
      return new Response("Not found", { status: 404 });
    }
    const auth = request.headers.get("Authorization");
    if (auth !== `Bearer ${env.VAULT_ADMIN_TOKEN}`) {
      return new Response("Unauthorized", { status: 401 });
    }
    await runRotation(env);
    return new Response(JSON.stringify({ ok: true }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

### wrangler.toml

```toml
name = "example project-vault"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding = "VAULT_KV"
id = "<vault_kv_namespace_id>"

[triggers]
crons = ["0 * * * *"]  # hourly rotation check
```

## Implementation Details

### Zero-downtime dual-version support

The grace period extends the old version's KV TTL by 5 minutes after rotation. Consumer Workers cache the secret for 30 seconds, so by the time all Workers have refreshed their in-process cache, the old version is still valid. The timeline:

```
t=0     New version written, current pointer updated
t=0–5m  Old version still KV-valid (grace period)
t=30s   Consumer Workers begin picking up new version (cache expiry)
t=5m    Old version KV entry expires
```

### Consuming secrets in other Workers

```typescript
// In any consumer Worker that has VAULT_KV bound:
import { getSecret } from "../vault/client";

export default {
  async fetch(request: Request, env: Env & { VAULT_KV: KVNamespace }) {
    const apiKey = await getSecret(env.VAULT_KV, "upstream_api_key");
    const resp = await fetch("https://upstream.example.com/api", {
      headers: { Authorization: `Bearer ${apiKey}` },
    });
    return resp;
  },
};
```

## Anti-patterns

- **Storing secret values as Wrangler secrets on the vault Worker itself** — the vault Worker should use Wrangler secrets only for the admin token and the endpoint used to mint new keys, never for the rotated secrets themselves.
- **Reading from KV on every subrequest** — KV adds ~50 ms latency. Always use the in-process cache with a reasonable TTL.
- **Setting the same KV TTL as the logical expiry** — if the rotation cron fails, the secret disappears before the next rotation window. Add buffer (grace + rotation interval) to the KV TTL.
- **Rotating all secrets simultaneously** — if the upstream key-minting service is rate-limited, stagger rotations using cron schedules per secret or add `await scheduler.wait()` between rotations.
- **Unbounded audit logs** — cap the KV audit log (e.g., 500 entries). Alternatively, stream audit entries to Analytics Engine for durable storage.

## Gotchas

- KV is eventually consistent across regions. After writing a new `current` pointer, a Worker in a distant PoP may still read the old version for up to ~60 seconds. The grace period absorbs this.
- The in-process module-level cache (`IN_PROCESS_CACHE`) is per-isolate. A Worker isolate is evicted after ~30 seconds of inactivity, so the cache is effectively a within-request-burst deduplicator, not a sustained cache.
- `kv.get(..., "json")` returns `null` (not throws) if the key is missing or the value is not valid JSON. Always check for null before destructuring.
- The rotation cron runs globally on Cloudflare's infrastructure, not at a specific PoP. If the upstream key-minting endpoint is geo-restricted, the cron may fail depending on which PoP runs it. Use a Smart Placement hint or proxy the request through a fixed origin.

## Verification

```bash
# Provision initial secret
curl -X POST https://vault.example.com/rotate \
  -H "Authorization: Bearer ${VAULT_ADMIN_TOKEN}"

# Read current version pointer
wrangler kv key get --namespace-id=<vault_kv_id> "secrets/upstream_api_key/current"

# Read version record
wrangler kv key get --namespace-id=<vault_kv_id> \
  "secrets/upstream_api_key/versions/$(wrangler kv key get --namespace-id=<vault_kv_id> secrets/upstream_api_key/current)"

# View audit log
wrangler kv key get --namespace-id=<vault_kv_id> "secrets/upstream_api_key/audit" | jq .

# Force rotation and verify new version
curl -X POST https://vault.example.com/rotate \
  -H "Authorization: Bearer ${VAULT_ADMIN_TOKEN}"
wrangler kv key get --namespace-id=<vault_kv_id> "secrets/upstream_api_key/current"
# Version timestamp should have advanced
```

## Related

- `documentation/docs/policies/infra/workers-terraform-cloudflare-provider.md`
- `documentation/docs/policies/infra/workers-cost-attribution-analytics-engine.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://developers.cloudflare.com/workers/configuration/secrets/
- https://developers.cloudflare.com/workers/runtime-apis/scheduled-event/

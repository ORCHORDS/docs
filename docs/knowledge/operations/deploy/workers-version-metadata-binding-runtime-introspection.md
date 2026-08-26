# Workers Version Metadata Binding: Runtime Introspection

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A request arrives at your Worker but your observability platform shows no deployment event for the version that handled it. You need to correlate live request traffic with exact deployment versions — not just the Worker name — to distinguish "slow because of bad code in v42" from "slow because of network conditions affecting all versions". You also want to route a subset of beta users to a newer version without a full gradual rollout, using the current version's identity as a routing signal inside the Worker itself.

## Context

Cloudflare Workers expose a `WorkerVersionMetadata` binding that gives a running Worker instance access to its own deployment metadata at runtime — not via an environment variable string, but through a typed binding with a structured API. The binding is declared in `wrangler.toml` and is available in any Worker regardless of whether Workers Versions (gradual rollout) is being used.

Available properties on the binding:
- `id` — the UUID of the specific version (matches the ID in `wrangler versions list` and the Cloudflare dashboard)
- `tag` — an optional string tag set at upload time via `wrangler versions upload --tag`
- `timestamp` — the ISO 8601 timestamp of when this version was uploaded

This is distinct from deploy tracking (recording a version ID to an external store after deploy); introspection is the version reading about itself at request time.

## Declaring the Binding

```toml
# wrangler.toml
name = "my-api"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[version_metadata]
binding = "CF_VERSION_METADATA"
```

The binding name is arbitrary; `CF_VERSION_METADATA` is a convention that makes its origin clear. One binding per Worker script; the binding is read-only.

## TypeScript Types and Basic Introspection

```typescript
// src/types.ts
export interface Env {
  CF_VERSION_METADATA: WorkerVersionMetadata;
  // other bindings...
}

// WorkerVersionMetadata is defined in @cloudflare/workers-types:
// interface WorkerVersionMetadata {
//   readonly id: string;
//   readonly tag: string;
//   readonly timestamp: string;
// }
```

```typescript
// src/index.ts
import type { Env } from './types';

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const version = env.CF_VERSION_METADATA;

    // Attach version metadata to every response for traceability
    const response = await handleRequest(request, env, ctx);
    const mutable = new Response(response.body, response);
    mutable.headers.set('X-Worker-Version-Id', version.id);
    mutable.headers.set('X-Worker-Version-Tag', version.tag || 'untagged');
    mutable.headers.set('X-Worker-Deployed-At', version.timestamp);
    return mutable;
  },
};

async function handleRequest(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
  // application logic
  return new Response('ok');
}
```

## Version-Aware Logging and Observability

Enrich every log line with the version ID so that log queries can be scoped to a specific deployment:

```typescript
// src/logger.ts
import type { Env } from './types';

export interface LogEntry {
  level: 'info' | 'warn' | 'error';
  message: string;
  versionId: string;
  versionTag: string;
  deployedAt: string;
  requestId: string;
  durationMs?: number;

}

export function createLogger(env: Env, requestId: string) {
  const meta = {
    versionId: env.CF_VERSION_METADATA.id,
    versionTag: env.CF_VERSION_METADATA.tag || 'untagged',
    deployedAt: env.CF_VERSION_METADATA.timestamp,
    requestId,
  };

  return {
    info(message: string, extra?: Record<string, unknown>): void {
      console.log(JSON.stringify({ level: 'info', message, ...meta, ...extra }));
    },
    warn(message: string, extra?: Record<string, unknown>): void {
      console.warn(JSON.stringify({ level: 'warn', message, ...meta, ...extra }));
    },
    error(message: string, extra?: Record<string, unknown>): void {
      console.error(JSON.stringify({ level: 'error', message, ...meta, ...extra }));
    },
  };
}
```

Usage in a fetch handler:

```typescript
import { createLogger } from './logger';
import type { Env } from './types';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const requestId = request.headers.get('cf-ray') ?? crypto.randomUUID();
    const log = createLogger(env, requestId);

    const start = Date.now();
    try {
      const res = await handleRequest(request, env);
      log.info('request completed', { status: res.status, durationMs: Date.now() - start });
      return res;
    } catch (err) {
      log.error('unhandled error', { error: String(err), durationMs: Date.now() - start });
      return new Response('Internal Server Error', { status: 500 });
    }
  },
};
```

## Version Tag-Based Feature Routing

Tag versions at upload time and use the tag at runtime to enable features for beta users:

```bash
# Upload version with a tag (does not deploy traffic to it)
npx wrangler versions upload --tag "beta-2026-08-23"

# Later, route 10% of traffic to this version
npx wrangler versions deploy \
  --version-id <id-from-upload> \
  --percentage 10
```

Inside the Worker, use the tag to adapt behavior without branching by environment variable:

```typescript
// src/features.ts
import type { Env } from './types';

type FeatureSet = {
  newCheckout: boolean;
  streamingResponse: boolean;
  analyticsV2: boolean;
};

export function getFeatures(env: Env, userId?: string): FeatureSet {
  const tag = env.CF_VERSION_METADATA.tag;
  const isBeta = tag.startsWith('beta-');
  const isCanary = tag.startsWith('canary-');

  return {
    // Only enable new checkout on beta or canary versions
    newCheckout: isBeta || isCanary,
    // Streaming is stable in all versions tagged post-August 2026
    streamingResponse: isTagAfter(tag, '2026-08-01'),
    // Analytics V2 only on beta, and only for specific user IDs
    analyticsV2: isBeta && isEnrolledUser(userId),
  };
}

function isTagAfter(tag: string, isoDate: string): boolean {
  // Tags must embed a date for this to work: "beta-2026-08-23", "stable-2026-07-15"
  const match = tag.match(/(\d{4}-\d{2}-\d{2})/);
  if (!match) return false;
  return match[1] >= isoDate;
}

function isEnrolledUser(userId?: string): boolean {
  if (!userId) return false;
  // Simple hash-based enrollment: users whose ID hashes to 0 mod 10
  const hash = [...userId].reduce((acc, c) => acc + c.charCodeAt(0), 0);
  return hash % 10 === 0;
}
```

## Introspection Endpoint for Diagnostics

Expose a `/__version` endpoint for internal use (gated by a secret header) to surface version metadata without needing dashboard access:

```typescript
// src/routes/version.ts
import type { Env } from '../types';

const INTERNAL_SECRET_HEADER = 'X-Internal-Token';

export async function handleVersionRoute(request: Request, env: Env): Promise<Response | null> {
  const url = new URL(request.url);
  if (url.pathname !== '/__version') return null;

  const token = request.headers.get(INTERNAL_SECRET_HEADER);
  const expectedToken = (env as unknown as { INTERNAL_TOKEN: string }).INTERNAL_TOKEN;

  if (!expectedToken || token !== expectedToken) {
    return new Response('Forbidden', { status: 403 });
  }

  const metadata = env.CF_VERSION_METADATA;
  const body = {
    id: metadata.id,
    tag: metadata.tag,
    timestamp: metadata.timestamp,
    uptime: Date.now() - new Date(metadata.timestamp).getTime(),
  };

  return new Response(JSON.stringify(body, null, 2), {
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'no-store',
    },
  });
}
```

## Anti-patterns

- **Using an environment variable (`VERSION_ID = "abc123"`) baked in at build time** — this requires a new build and deploy for each version, and the variable is identical across all instances of that deploy. The binding, by contrast, reflects the actual running version even when a previous version is still serving traffic during a gradual rollout.
- **Reading `CF_VERSION_METADATA.id` as a substitute for feature flags** — version IDs are opaque UUIDs. They have no semantic meaning unless paired with a registry mapping them to capabilities. Use tags for semantic routing; use IDs for correlation and audit.
- **Exposing the version endpoint without authentication** — version metadata exposes deployment timing and internal tagging conventions to unauthenticated callers.

## Gotchas

- `WorkerVersionMetadata` is only available when the `[version_metadata]` stanza is present in `wrangler.toml`. Omitting it means `env.CF_VERSION_METADATA` is `undefined` at runtime, not a typed error at build time.
- In local development with `wrangler dev`, the `id` is a placeholder value (not a real UUID from the Cloudflare backend), and `tag` is an empty string. Guard against this in code that routes based on tag content.
- The `timestamp` field reflects the version upload time, not the time traffic was shifted to it via `wrangler versions deploy`. If a version was uploaded an hour before rollout, the timestamp will be an hour old when the first request arrives.
- `@cloudflare/workers-types` must be at version 4.20240909.0 or later for `WorkerVersionMetadata` to be included. Older type packages define the binding as `unknown`.

## Verification

```bash
# After deploy, hit the diagnostic endpoint
curl -H "X-Internal-Token: $INTERNAL_TOKEN" https://my-api.example.com/__version

# Expected output:
# {
#   "id": "a1b2c3d4-...",
#   "tag": "stable-2026-08-23",
#   "timestamp": "2026-08-23T14:00:00.000Z",
#   "uptime": 3600000
# }

# Cross-reference with wrangler
npx wrangler versions list --name my-api
# Confirm the id matches the version currently receiving 100% of traffic
```

## Related

- `workers-version-metadata-binding-deploy-tracking.md`
- `worker-versioning-gradual-rollout.md`
- `workers-tail-sampling-progressive-rollout.md`
- `cloudflare-analytics-engine-deploy-observability.md`
- `wrangler-versions-api-rollback-automation.md`

## Sources

- WorkerVersionMetadata binding reference: https://developers.cloudflare.com/workers/runtime-apis/bindings/version-metadata/
- Workers Versions (gradual rollout): https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
- `wrangler versions upload`: https://developers.cloudflare.com/workers/wrangler/commands/#versions-upload
- `@cloudflare/workers-types` changelog: https://github.com/cloudflare/workers-types/releases

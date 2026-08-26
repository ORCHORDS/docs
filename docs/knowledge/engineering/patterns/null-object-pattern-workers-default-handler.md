# Null Object Pattern: Workers Default Handler

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Route handlers, middleware chains, and service bindings in Cloudflare Workers often need optional dependencies — a logger, a rate-limiter, or a feature-flagging service — that may not be configured in every environment (local dev, staging, production). Littering the codebase with `if (logger) logger.log(...)` or `service?.rateLimit()` guards makes control flow noisy and hides the real logic. Null checks that silently swallow errors in one environment cause cryptic failures in another when the real implementation is wired in.

## Context

Workers environments differ across `wrangler dev`, preview branches, and production: bindings declared in `wrangler.toml` may not exist in all environments, feature flags may disable entire service integrations, and test harnesses need to stub dependencies without importing real Cloudflare runtime objects. The Null Object pattern replaces `null`/`undefined` checks with a do-nothing implementation that satisfies the same interface, making optional services safe to call unconditionally.

## Defining the Interface and a Real Implementation

Start with a TypeScript interface so both the real implementation and the null object are contractually equivalent.

```typescript
// src/services/analytics.ts

export interface AnalyticsService {
  trackEvent(name: string, properties: Record<string, unknown>): Promise<void>;
  flush(): Promise<void>;
}

// Real implementation backed by a KV write-behind buffer
export class KvAnalyticsService implements AnalyticsService {
  constructor(private kv: KVNamespace, private userId: string) {}

  async trackEvent(
    name: string,
    properties: Record<string, unknown>
  ): Promise<void> {
    const key = `analytics:${this.userId}:${Date.now()}`;
    await this.kv.put(key, JSON.stringify({ name, properties }), {
      expirationTtl: 86400,
    });
  }

  async flush(): Promise<void> {
    // real flush logic — batch send to downstream
  }
}
```

## The Null Object Implementation

The null object satisfies `AnalyticsService` but performs no work. It is not a stub — it has no expectations and does not record calls. It is safe to use in any environment.

```typescript
// src/services/null-analytics.ts
import type { AnalyticsService } from './analytics';

export class NullAnalyticsService implements AnalyticsService {
  async trackEvent(
    _name: string,
    _properties: Record<string, unknown>
  ): Promise<void> {
    // intentionally no-op
  }

  async flush(): Promise<void> {
    // intentionally no-op
  }
}

// Singleton — allocate once per isolate, not per request
export const NULL_ANALYTICS: AnalyticsService = new NullAnalyticsService();
```

## Factory — Choosing the Right Implementation

A factory function reads the environment binding and returns either the real service or the null object. Callers never inspect bindings directly.

```typescript
// src/services/analytics-factory.ts
import type { Env } from '../env';
import { KvAnalyticsService, type AnalyticsService } from './analytics';
import { NULL_ANALYTICS } from './null-analytics';

export function makeAnalytics(userId: string, env: Env): AnalyticsService {
  // KV binding absent in local dev or when feature is disabled
  if (!env.ANALYTICS_KV) return NULL_ANALYTICS;
  return new KvAnalyticsService(env.ANALYTICS_KV, userId);
}
```

```typescript
// src/env.ts
export interface Env {
  DB: D1Database;
  ANALYTICS_KV?: KVNamespace;   // optional — absent in local dev
  FEATURE_FLAGS?: KVNamespace;
}
```

## Applying the Pattern to Request Handlers

Handlers receive an `AnalyticsService` with no null checks. Business logic reads cleanly.

```typescript
// src/handlers/post.ts
import type { Env } from '../env';
import type { AnalyticsService } from '../services/analytics';
import { makeAnalytics } from '../services/analytics-factory';

export async function handleCreatePost(
  req: Request,
  env: Env
): Promise<Response> {
  const userId = req.headers.get('x-user-id') ?? 'anon';
  const analytics: AnalyticsService = makeAnalytics(userId, env);

  const body = await req.json<{ text: string }>();

  // No null checks anywhere below this line
  await analytics.trackEvent('post.create.attempt', { userId });

  const postId = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO posts (id, author_id, body, created_at)
     VALUES (?, ?, ?, ?)`
  ).bind(postId, userId, body.text, new Date().toISOString()).run();

  await analytics.trackEvent('post.create.success', { userId, postId });
  await analytics.flush();

  return Response.json({ postId }, { status: 201 });
}
```

## Null Object for Service Bindings

Service bindings between Workers can also be absent in some environments. Wrap them with a null object so the calling Worker does not need routing-layer conditionals.

```typescript
// src/services/moderation-service.ts
export interface ModerationService {
  check(text: string): Promise<{ flagged: boolean; reason?: string }>;
}

export class NullModerationService implements ModerationService {
  async check(_text: string) {
    return { flagged: false };
  }
}

// src/services/moderation-factory.ts
import type { Env } from '../env';
import type { ModerationService } from './moderation-service';
import { NullModerationService } from './moderation-service';

export function makeModeration(env: Env): ModerationService {
  // In production, MODERATION is a service binding to a separate Worker
  if (!env.MODERATION) return new NullModerationService();
  return {
    async check(text: string) {
      const resp = await env.MODERATION!.fetch(
        new Request('https://moderation/check', {
          method: 'POST',
          body: JSON.stringify({ text }),
        })
      );
      return resp.json<{ flagged: boolean; reason?: string }>();
    },
  };
}
```

## Anti-patterns

- Using `null` or `undefined` as the "no-op" value and scattering `?.` optional chaining everywhere
- Creating a null object with `console.log` statements — noise in production logs; keep it silent
- Sharing mutable state in the null object singleton (e.g. a counter array) — isolates are shared, state leaks
- Returning a null object when the binding is present but misconfigured — use a strict startup check for required bindings
- Treating the null object as a test mock — use proper test doubles with assertion capabilities for unit tests

## Gotchas

- `env.BINDING` evaluates to `undefined`, not `null`, when a binding is absent; use `!env.BINDING` not `env.BINDING === null`
- Optional service bindings (`?:` in the Env type) must be declared as optional in `wrangler.toml` too, or the Worker will fail to start locally
- Null objects that implement async methods must still return `Promise<void>`; returning synchronously breaks callers that `await` them
- If the interface grows (new method added), TypeScript will catch missing implementations on the null object at compile time — a feature, not a bug
- Do not use the null object pattern for required dependencies — fail fast with a startup assertion instead

## Verification

```typescript
// src/services/__tests__/null-analytics.test.ts
import { describe, it, expect, vi } from 'vitest';
import { NULL_ANALYTICS } from '../null-analytics';

describe('NullAnalyticsService', () => {
  it('trackEvent resolves without throwing', async () => {
    await expect(
      NULL_ANALYTICS.trackEvent('test', { key: 'value' })
    ).resolves.toBeUndefined();
  });

  it('flush resolves without throwing', async () => {
    await expect(NULL_ANALYTICS.flush()).resolves.toBeUndefined();
  });

  it('is the same reference across calls (singleton)', () => {
    const { NULL_ANALYTICS: a } = require('../null-analytics');
    const { NULL_ANALYTICS: b } = require('../null-analytics');
    expect(a).toBe(b);
  });
});
```

```bash
# Integration: run locally without ANALYTICS_KV binding — should not error
wrangler dev --local
curl -X POST http://localhost:8787/posts \
  -H 'x-user-id: u1' -d '{"text":"hello"}'
# Expect 201 with no KV errors in logs
```

## Related

- `documentation/docs/policies/patterns/dependency-injection.md`
- `documentation/docs/policies/patterns/strategy-pattern-workers-kv.md`
- `documentation/docs/policies/patterns/proxy-pattern-workers-service-binding-auth.md`
- `documentation/docs/policies/patterns/template-method-pattern-workers-handler.md`
- `documentation/docs/policies/patterns/graceful-degradation.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- https://developers.cloudflare.com/kv/api/
- https://refactoring.guru/design-patterns/null-object
- https://www.typescriptlang.org/docs/handbook/2/objects.html#optional-properties

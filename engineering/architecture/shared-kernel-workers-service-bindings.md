# Shared Kernel Pattern with Workers Service Bindings

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Two or more bounded contexts in the example project platform need to share a small, carefully curated set of
domain types — value objects, identifiers, enums, validation logic — without one context owning the
other or creating a general-purpose utility library that becomes a dumping ground. Classic examples:
the `TenantId`, `UserId`, and `Money` value objects are needed by the Billing Worker, the
Entitlements Worker, and the Notification Worker, yet each context must remain independently
deployable. DDD calls this subset of shared types the **Shared Kernel**.

## Context

In a monolith the Shared Kernel is a package or module compiled together with every consumer. On
Cloudflare Workers the unit of deployment is a Worker script. Shared Kernel types are distributed
either as an npm package bundled into each Worker at build time, or as a dedicated kernel Worker
whose logic is called via Service Bindings (Worker-to-Worker RPC). This article covers both models,
their tradeoffs, and the governance rules that keep the kernel from bloating.

---

## Model 1 — Bundled npm Package (Preferred for Pure Types)

The kernel is a TypeScript package with zero runtime dependencies published to the internal registry
(or a monorepo workspace). It contains **only** pure value objects, branded types, and validation
functions — no I/O, no fetch, no D1.

```typescript
// packages/shared-kernel/src/tenant-id.ts
declare const __brand: unique symbol;
type Brand<T, B> = T & { [__brand]: B };

export type TenantId = Brand<string, 'TenantId'>;

export function TenantId(raw: string): TenantId {
  if (!/^ten_[a-z0-9]{16}$/.test(raw)) {
    throw new TypeError(`Invalid TenantId: ${raw}`);
  }
  return raw as TenantId;
}

export function isTenantId(value: unknown): value is TenantId {
  return typeof value === 'string' && /^ten_[a-z0-9]{16}$/.test(value);
}
```

```typescript
// packages/shared-kernel/src/money.ts
import { z } from 'zod';

export const MoneySchema = z.object({
  amount:   z.number().int().nonnegative(),  // cents
  currency: z.enum(['USD', 'EUR', 'GBP']),
});

export type Money = z.infer<typeof MoneySchema>;

export function addMoney(a: Money, b: Money): Money {
  if (a.currency !== b.currency) throw new Error('Currency mismatch');
  return { amount: a.amount + b.amount, currency: a.currency };
}

export function formatMoney(m: Money): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: m.currency,
    minimumFractionDigits: 2,
  }).format(m.amount / 100);
}
```

```json
// packages/shared-kernel/package.json
{
  "name": "@example project/shared-kernel",
  "version": "1.4.0",
  "exports": {
    ".": "./dist/index.js",
    "./tenant-id": "./dist/tenant-id.js",
    "./money": "./dist/money.js"
  },
  "sideEffects": false
}
```

Each Worker adds `@example project/shared-kernel` as a dependency. Wrangler bundles it at build time, so each
Worker ships its own copy. This is intentional: you avoid runtime coupling and cross-Worker version
skew at the cost of slightly larger bundle sizes (typically < 5 KB gzipped).

---

## Model 2 — Kernel Worker via Service Binding (For Shared Behaviour)

When the kernel needs stateful or I/O-backed logic — e.g. resolving a `TenantId` to its canonical
plan tier from D1 — a dedicated Kernel Worker exposes typed RPC methods via Service Bindings.

```typescript
// workers/kernel/src/index.ts
import { WorkerEntrypoint } from 'cloudflare:workers';
import type { D1Database } from '@cloudflare/workers-types';
import { TenantId, isTenantId } from '@example project/shared-kernel/tenant-id';

interface Env {
  DB: D1Database;
}

export class KernelService extends WorkerEntrypoint<Env> {
  /**
   * Resolve a TenantId to its current plan tier.
   * Called via Service Binding from Billing, Entitlements, Notification workers.
   */
  async getTenantPlan(rawId: string): Promise<{ plan: string; features: string[] }> {
    if (!isTenantId(rawId)) throw new TypeError(`Invalid TenantId: ${rawId}`);

    const row = await this.env.DB
      .prepare('SELECT plan, features FROM tenant_plans WHERE tenant_id = ?')
      .bind(rawId)
      .first<{ plan: string; features: string }>();

    if (!row) throw new Error(`Tenant not found: ${rawId}`);
    return { plan: row.plan, features: JSON.parse(row.features) };
  }

  /**
   * Validate and normalise a Money object.
   * Centralised so rounding rules are applied consistently.
   */
  async normaliseMoney(amount: number, currency: string): Promise<{ amount: number; currency: string }> {
    const allowed = ['USD', 'EUR', 'GBP'];
    if (!allowed.includes(currency)) throw new TypeError(`Unsupported currency: ${currency}`);
    // Round to nearest cent using banker's rounding
    const rounded = Math.round(amount);
    return { amount: rounded, currency };
  }
}

export default {
  fetch(): Response {
    return new Response('Kernel RPC only — use Service Binding', { status: 405 });
  },
};
```

```jsonc
// workers/kernel/wrangler.jsonc
{
  "name": "example project-kernel",
  "main": "src/index.ts",
  "compatibility_date": "2025-08-01",
  "d1_databases": [
    { "binding": "DB", "database_id": "kernel-db" }
  ]
}
```

```typescript
// workers/billing/src/index.ts — consumer side
import type { KernelService } from '../../kernel/src/index';

interface Env {
  KERNEL: Service<KernelService>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const tenantId = new URL(request.url).searchParams.get('tenant') ?? '';
    const { plan, features } = await env.KERNEL.getTenantPlan(tenantId);
    return Response.json({ plan, features });
  },
};
```

```jsonc
// workers/billing/wrangler.jsonc
{
  "name": "example project-billing",
  "main": "src/index.ts",
  "services": [
    { "binding": "KERNEL", "service": "example project-kernel" }
  ]
}
```

Service Binding RPC calls are in-process on the same PoP with no network hop. Round-trip latency is
< 1 ms for simple calls; D1 latency dominates for queries.

---

## Governance Rules for the Shared Kernel

```typescript
// scripts/validate-kernel-imports.ts
// Run in CI: tsx scripts/validate-kernel-imports.ts
import { readFileSync, readdirSync } from 'fs';
import { join } from 'path';

const ALLOWED_KERNEL_DEPS = ['zod', 'date-fns'];

const pkgJson = JSON.parse(
  readFileSync(join(__dirname, '../packages/shared-kernel/package.json'), 'utf8'),
);

const forbidden = Object.keys(pkgJson.dependencies ?? {}).filter(
  (dep) => !ALLOWED_KERNEL_DEPS.includes(dep),
);

if (forbidden.length > 0) {
  console.error(`Shared kernel has forbidden dependencies: ${forbidden.join(', ')}`);
  process.exit(1);
}

console.log('Shared kernel dependency audit passed.');
```

Governance checklist enforced in PR review:
- No I/O (fetch, D1, KV) in the bundled package model.
- No business logic that belongs to a single bounded context.
- Kernel package changes require sign-off from all consuming teams.
- Kernel Worker RPC surface is versioned with a deprecation window of ≥ 2 sprints.

---

## Versioning the Kernel Worker

When a breaking change is needed (e.g. `getTenantPlan` returns a new field), use additive versioning
rather than replacing the method:

```typescript
// workers/kernel/src/index.ts (versioned extension)
export class KernelService extends WorkerEntrypoint<Env> {
  // Original method — kept for backwards compat
  async getTenantPlan(rawId: string): Promise<{ plan: string; features: string[] }> {
    const result = await this.getTenantPlanV2(rawId);
    return { plan: result.plan, features: result.features };
  }

  // New method with richer return type
  async getTenantPlanV2(rawId: string): Promise<{
    plan: string;
    features: string[];
    trialEndsAt: number | null;
  }> {
    // implementation
    return { plan: 'pro', features: ['x'], trialEndsAt: null };
  }
}
```

Old consumers call `getTenantPlan`; new consumers call `getTenantPlanV2`. Deprecate the old method
after all consumers migrate; remove after two deploy cycles.

---

## Anti-patterns

- **Expanding the kernel into a general utility library**: Every team adds "just one more util" and
  the kernel becomes a monolith that all teams depend on and none own. Enforce the governance
  checklist in CI.
- **Calling the Kernel Worker from a Durable Object alarm handler**: Alarm handlers have a 15-second
  CPU budget and the DO may be on a different PoP than the Kernel Worker's subrequest target. Prefer
  bundled pure functions in DO code.
- **Version-locking consumers to the kernel**: Pin the kernel npm package with a caret range
  (`^1.4.0`), not an exact pin, so patch releases propagate automatically without PRs per consumer.
- **Putting domain logic in the kernel**: `calculateInvoiceTax` is Billing's responsibility, not the
  kernel's. The kernel holds shared *structure*, not shared *process*.
- **Service Binding call inside a hot path without caching**: `getTenantPlan` is called on every
  request — cache the result in a request-scoped variable or a short-lived KV entry.

---

## Gotchas

- Service Bindings are resolved at deploy time. If the Kernel Worker name changes, all consuming
  Workers must be redeployed before the binding resolves correctly.
- `WorkerEntrypoint` RPC methods must return JSON-serialisable values (or `Response` /
  `ReadableStream`). Returning class instances with methods will silently lose the prototype.
- TypeScript types for the Kernel Worker are only available when consumers reference the source file
  directly (monorepo) or import a published `.d.ts` package. Without them, `env.KERNEL` is typed as
  `Fetcher`, not `Service<KernelService>`, and you lose autocomplete.
- The bundled package model means each Worker ships its own version of the kernel. If two Workers
  are at different kernel versions and exchange data serialised by kernel types, the validation rules
  may diverge. Pin minor versions together in your monorepo toolchain.
- Wrangler local dev (`--local`) resolves Service Bindings by name against other locally-running
  Workers. Start the Kernel Worker first, or use `wrangler dev --remote` for integration tests.

---

## Verification

```bash
# Confirm the kernel package has no forbidden runtime deps
tsx scripts/validate-kernel-imports.ts

# Integration smoke test via wrangler
wrangler dev workers/kernel/wrangler.jsonc --port 8788 &
wrangler dev workers/billing/wrangler.jsonc --port 8787

curl "http://localhost:8787/?tenant=ten_abc1234567890abc"
# Expected: {"plan":"pro","features":["feature_a","feature_b"]}

# Check bundle sizes stay under threshold
wrangler publish --dry-run workers/billing/wrangler.jsonc 2>&1 | grep 'Total Upload'
# Expected: < 150 KiB
```

---

## Related

- `/documentation/categories/architecture/worker-to-worker-rpc-service-bindings.md`
- `/documentation/categories/architecture/ddd-bounded-contexts-context-mapping.md`
- `/documentation/categories/architecture/bounded-context-design.md`
- `/documentation/categories/architecture/domain-driven-design-basics.md`
- `/documentation/categories/architecture/proxy-pattern-workers-service-binding-abstraction.md`

---

## Sources

- Cloudflare Service Bindings RPC: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/rpc/
- WorkerEntrypoint API: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/rpc/#workersrpc
- Eric Evans — "Domain-Driven Design: Tackling Complexity in the Heart of Software" (Shared Kernel chapter)
- Vaughn Vernon — "Implementing Domain-Driven Design" (context mapping patterns)

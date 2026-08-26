# Pipes and Filters Pattern on Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A single Worker handler grows into a monolithic function that validates, transforms,
enriches, authorises, logs, and then responds — all inline. Adding a new processing
step forces edits inside existing logic, making testing and reordering hard. You need
a way to chain discrete, independently testable transformation stages over a request or
a data record without coupling them to one another.

## Context

The Pipes and Filters architectural pattern models processing as a sequence of
*filters* (pure transformation units) connected by *pipes* (the data carrier that
flows from one filter to the next). On Workers the "pipe" is usually a plain object
(or `Request` / `Response`) passed synchronously or asynchronously through an ordered
array of filters. Because Workers run in isolates with a single-threaded event loop,
all filters share the same CPU budget; the pattern is therefore most useful for
per-request enrichment pipelines, ETL record processing triggered by a Queue consumer,
or multi-stage content transformation before writing to R2/D1.

The pattern differs from the Decorator pattern (which wraps behaviour around a fixed
core) and from middleware chains (which control whether to call `next()`). Pipes and
Filters are about *data transformation*: each filter receives a context object, mutates
or replaces it, and returns the result for the next stage.

## Defining the Pipeline Primitives

```typescript
// pipeline.ts
export type FilterFn<T> = (ctx: T) => T | Promise<T>;

export async function runPipeline<T>(
  initial: T,
  filters: FilterFn<T>[],
): Promise<T> {
  let ctx = initial;
  for (const filter of filters) {
    ctx = await filter(ctx);
  }
  return ctx;
}

// Combine two pipelines at build time
export function compose<T>(...pipelines: FilterFn<T>[][]): FilterFn<T>[] {
  return pipelines.flat();
}
```

## Request Enrichment Pipeline

```typescript
// filters/request-pipeline.ts
import { runPipeline, FilterFn } from './pipeline';

interface RequestCtx {
  request: Request;
  url: URL;
  tenantId: string | null;
  userId: string | null;
  rateLimitOk: boolean;
  body: unknown;
}

const parseUrl: FilterFn<RequestCtx> = (ctx) => ({
  ...ctx,
  url: new URL(ctx.request.url),
});

const extractTenant: FilterFn<RequestCtx> = (ctx) => ({
  ...ctx,
  tenantId: ctx.request.headers.get('X-Tenant-Id'),
});

const verifyJwt =
  (kv: KVNamespace): FilterFn<RequestCtx> =>
  async (ctx) => {
    const token = ctx.request.headers.get('Authorization')?.replace('Bearer ', '');
    if (!token) return { ...ctx, userId: null };
    const cached = await kv.get(`jwt:${token}`, 'json') as { sub: string } | null;
    return { ...ctx, userId: cached?.sub ?? null };
  };

const enforceRateLimit =
  (kv: KVNamespace): FilterFn<RequestCtx> =>
  async (ctx) => {
    if (!ctx.tenantId) return { ...ctx, rateLimitOk: false };
    const key = `rl:${ctx.tenantId}`;
    const count = Number(await kv.get(key)) || 0;
    if (count >= 1000) return { ...ctx, rateLimitOk: false };
    await kv.put(key, String(count + 1), { expirationTtl: 60 });
    return { ...ctx, rateLimitOk: true };
  };

const parseBody: FilterFn<RequestCtx> = async (ctx) => {
  if (ctx.request.method === 'GET') return ctx;
  try {
    const body = await ctx.request.clone().json();
    return { ...ctx, body };
  } catch {
    return { ...ctx, body: null };
  }
};

export async function processRequest(
  request: Request,
  kv: KVNamespace,
): Promise<RequestCtx> {
  const initial: RequestCtx = {
    request,
    url: new URL(request.url),
    tenantId: null,
    userId: null,
    rateLimitOk: false,
    body: null,
  };

  return runPipeline(initial, [
    parseUrl,
    extractTenant,
    verifyJwt(kv),
    enforceRateLimit(kv),
    parseBody,
  ]);
}
```

## ETL Record Pipeline (Queue Consumer)

```typescript
// filters/etl-pipeline.ts
import { runPipeline, FilterFn } from './pipeline';

interface Record {
  raw: string;
  parsed: Record<string, unknown> | null;
  validated: boolean;
  enriched: Record<string, unknown> | null;
  normalized: Record<string, unknown> | null;
  errors: string[];
}

const parseJson: FilterFn<Record> = (ctx) => {
  try {
    return { ...ctx, parsed: JSON.parse(ctx.raw) };
  } catch (e) {
    return { ...ctx, errors: [...ctx.errors, 'JSON parse failed'] };
  }
};

const validate: FilterFn<Record> = (ctx) => {
  if (!ctx.parsed) return ctx;
  const required = ['id', 'type', 'timestamp'];
  const missing = required.filter((k) => !(k in ctx.parsed!));
  if (missing.length > 0) {
    return {
      ...ctx,
      validated: false,
      errors: [...ctx.errors, `Missing fields: ${missing.join(', ')}`],
    };
  }
  return { ...ctx, validated: true };
};

const enrich =
  (db: D1Database): FilterFn<Record> =>
  async (ctx) => {
    if (!ctx.validated || !ctx.parsed) return ctx;
    const id = ctx.parsed['id'] as string;
    const row = await db
      .prepare('SELECT metadata FROM entities WHERE id = ?')
      .bind(id)
      .first<{ metadata: string }>();
    return {
      ...ctx,
      enriched: { ...ctx.parsed, metadata: row ? JSON.parse(row.metadata) : null },
    };
  };

const normalize: FilterFn<Record> = (ctx) => {
  if (!ctx.enriched) return ctx;
  return {
    ...ctx,
    normalized: {
      ...ctx.enriched,
      timestamp: new Date(ctx.enriched['timestamp'] as string).toISOString(),
    },
  };
};

export async function processRecord(
  raw: string,
  db: D1Database,
): Promise<Record> {
  return runPipeline(
    { raw, parsed: null, validated: false, enriched: null, normalized: null, errors: [] },
    [parseJson, validate, enrich(db), normalize],
  );
}
```

## Conditional and Short-Circuit Filters

```typescript
// filters/conditional.ts
import { FilterFn } from './pipeline';

// Skip remaining filters if predicate is true
export function shortCircuit<T>(
  predicate: (ctx: T) => boolean,
): FilterFn<T> {
  return (ctx) => {
    if (predicate(ctx)) throw new ShortCircuitSignal(ctx);
    return ctx;
  };
}

export class ShortCircuitSignal<T> {
  constructor(public readonly ctx: T) {}
}

// Wrap runPipeline to handle short-circuit cleanly
export async function runPipelineGuarded<T>(
  initial: T,
  filters: FilterFn<T>[],
): Promise<T> {
  try {
    let ctx = initial;
    for (const filter of filters) {
      ctx = await filter(ctx);
    }
    return ctx;
  } catch (e) {
    if (e instanceof ShortCircuitSignal) return e.ctx as T;
    throw e;
  }
}

// Usage: reject unauthenticated requests early
interface AuthCtx { userId: string | null; response?: Response }
const rejectUnauth: FilterFn<AuthCtx> = shortCircuit(
  (ctx) => ctx.userId === null,
);
```

## Anti-patterns

- **Mutable shared state inside filters** — filters must be pure or side-effect-isolated;
  sharing mutable objects between filters creates order-dependency bugs that are
  invisible during individual filter tests.
- **Side effects in every filter** — performing D1 writes or Queue sends from multiple
  filters instead of accumulating intent in the context and flushing once at the end
  defeats the pattern's testability advantage.
- **Deep-cloning large context objects** on every step — spread syntax is fine for flat
  objects, but large nested trees should use an `updates` map accumulated over the
  pipeline and merged once at the end.
- **Filter arrays built inside hot paths** — constructing filter arrays on every request
  allocates garbage; build them once at module scope and close over environment bindings.

## Gotchas

- Workers do not support Node.js `stream.Transform`; the pattern must be implemented
  imperatively (loop + await) rather than with pipe-able streams.
- If a filter throws, the pipeline aborts. Wrap individual filters with try/catch when
  partial results should still flow downstream.
- The context object is the contract between filters. Versioning it (adding optional
  fields) is safe; removing or renaming fields is a breaking change for all downstream
  filters.
- `runPipeline` is generic but TypeScript will infer `T` from `initial`; ensure the
  initial value contains all fields that downstream filters expect, even if `null`.

## Verification

```typescript
// __tests__/pipeline.test.ts
import { runPipeline } from '../pipeline';

test('filters execute in order', async () => {
  const order: number[] = [];
  const f1 = (ctx: number) => { order.push(1); return ctx + 1; };
  const f2 = (ctx: number) => { order.push(2); return ctx + 10; };
  const result = await runPipeline(0, [f1, f2]);
  expect(result).toBe(11);
  expect(order).toEqual([1, 2]);
});

test('async filters are awaited before next runs', async () => {
  const f1 = async (ctx: number) => { await new Promise(r => setTimeout(r, 0)); return ctx + 1; };
  const f2 = (ctx: number) => ctx * 2;
  expect(await runPipeline(3, [f1, f2])).toBe(8);
});

test('individual filters are testable in isolation', async () => {
  const validate = (ctx: { value: number; valid: boolean }) =>
    ctx.value > 0 ? { ...ctx, valid: true } : ctx;
  expect(validate({ value: 5, valid: false })).toEqual({ value: 5, valid: true });
  expect(validate({ value: -1, valid: false })).toEqual({ value: -1, valid: false });
});
```

## Related

- `decorator-pattern-workers-middleware-composition.md`
- `template-method-pattern-workers-handler.md`
- `correlation-id-propagation-workers.md`
- `event-sourcing-cloudflare-workers-d1.md`
- `fan-out-queues-workers.md`

## Sources

- Pattern of Enterprise Application Architecture — Fowler (Pipes and Filters)
- Cloudflare Workers Runtime API — https://developers.cloudflare.com/workers/runtime-apis/
- TypeScript generic constraints — https://www.typescriptlang.org/docs/handbook/2/generics.html

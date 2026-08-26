# TypeScript Stage-3 Decorators for Class-Based Routing in Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to organise Cloudflare Workers request handling as classes with method-level
`@Get`, `@Post`, and `@Route` decorators instead of a flat `switch` or URL-matching chain.
The goal is co-located route metadata, middleware, and handlers without pulling in a full
framework like NestJS or adding `reflect-metadata` (which is not available in the Workers
runtime).

## Context

TypeScript 5.0+ supports the stage-3 ECMAScript decorator proposal without the legacy
`experimentalDecorators` flag. Stage-3 decorators use a different calling convention from
the old TS 4.x experimental ones: they receive a `ClassMethodDecoratorContext` or
`ClassDecoratorContext` object rather than `(target, key, descriptor)`. esbuild ≥ 0.19
emits stage-3 decorator output natively when `target` is `ES2022`+. No `reflect-metadata`
polyfill is needed — metadata is stored on the class constructor's own `Symbol` property.
Workers supports this because it runs a V8 version that implements the proposal.

## 1. tsconfig and wrangler.toml Setup

```jsonc
// tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022"],
    "moduleResolution": "bundler",
    "strict": true
    // Do NOT set "experimentalDecorators": true — use stage-3 instead
  }
}
```

```toml
# wrangler.toml
name = "router-worker"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]

[build]
command = "tsc --noEmit && esbuild src/index.ts --bundle --outfile=dist/worker.js --platform=browser --target=es2022 --format=esm"
```

## 2. Metadata Storage Helper

Store route metadata on the class constructor without `reflect-metadata`:

```typescript
// src/routing/metadata.ts
export interface RouteDefinition {
  method: string;
  path: string;
  handlerKey: string | symbol;
}

const ROUTES_KEY = Symbol('routes');

export function getRoutes(target: Function): RouteDefinition[] {
  return (target as any)[ROUTES_KEY] ?? [];
}

function addRoute(target: Function, def: RouteDefinition): void {
  const existing: RouteDefinition[] = (target as any)[ROUTES_KEY] ?? [];
  (target as any)[ROUTES_KEY] = [...existing, def];
}

// Stage-3 method decorator factory
export function Route(method: string, path: string) {
  return function <T extends (req: Request, ...args: any[]) => Response | Promise<Response>>(
    _target: T,
    ctx: ClassMethodDecoratorContext<any, T>,
  ) {
    ctx.addInitializer(function (this: any) {
      addRoute(this.constructor, {
        method: method.toUpperCase(),
        path,
        handlerKey: ctx.name,
      });
    });
  };
}

export const Get  = (path: string) => Route('GET',  path);
export const Post = (path: string) => Route('POST', path);
export const Put  = (path: string) => Route('PUT',  path);
export const Del  = (path: string) => Route('DELETE', path);
```

## 3. Controller Class

```typescript
// src/controllers/users.ts
import { Get, Post } from '../routing/metadata';

export class UsersController {
  constructor(private readonly env: Env) {}

  @Get('/users')
  async listUsers(req: Request): Promise<Response> {
    const results = await this.env.DB.prepare('SELECT id, name FROM users').all();
    return Response.json(results.results);
  }

  @Post('/users')
  async createUser(req: Request): Promise<Response> {
    const { name, email } = await req.json<{ name: string; email: string }>();
    const stmt = this.env.DB.prepare('INSERT INTO users (name, email) VALUES (?, ?) RETURNING id');
    const row = await stmt.bind(name, email).first<{ id: number }>();
    return Response.json({ id: row!.id }, { status: 201 });
  }

  @Get('/users/:id')
  async getUser(req: Request, params: Record<string, string>): Promise<Response> {
    const user = await this.env.DB
      .prepare('SELECT * FROM users WHERE id = ?')
      .bind(params.id)
      .first();
    if (!user) return new Response('Not found', { status: 404 });
    return Response.json(user);
  }
}
```

## 4. Router Assembly

```typescript
// src/routing/router.ts
import { getRoutes, RouteDefinition } from './metadata';

type ControllerCtor = new (env: Env) => object;

interface CompiledRoute {
  method: string;
  pattern: URLPattern;
  handler: (req: Request, params: Record<string, string>) => Promise<Response>;
}

export class ClassRouter {
  private readonly routes: CompiledRoute[] = [];

  register(Ctor: ControllerCtor, env: Env): void {
    const instance = new Ctor(env);
    const defs: RouteDefinition[] = getRoutes(Ctor);
    for (const def of defs) {
      this.routes.push({
        method: def.method,
        pattern: new URLPattern({ pathname: def.path }),
        handler: async (req, params) =>
          (instance as any)def.handlerKey,
      });
    }
  }

  async handle(req: Request): Promise<Response> {
    const url = new URL(req.url);
    for (const route of this.routes) {
      if (route.method !== req.method) continue;
      const match = route.pattern.exec({ pathname: url.pathname });
      if (match) {
        const params = match.pathname.groups as Record<string, string>;
        return route.handler(req, params);
      }
    }
    return new Response('Not found', { status: 404 });
  }
}
```

## 5. Worker Entry Point

```typescript
// src/index.ts
import { ClassRouter } from './routing/router';
import { UsersController } from './controllers/users';

let router: ClassRouter | null = null;

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    // Build router once per isolate lifetime
    if (!router) {
      router = new ClassRouter();
      router.register(UsersController, env);
    }
    return router.handle(req);
  },
} satisfies ExportedHandler<Env>;
```

## 6. Vitest Unit Test

```typescript
// src/controllers/users.test.ts
import { describe, it, expect, beforeEach } from 'vitest';
import { SELF } from 'cloudflare:test';

describe('UsersController', () => {
  it('GET /users returns JSON array', async () => {
    const res = await SELF.fetch('http://example.com/users');
    expect(res.status).toBe(200);
    const body = await res.json<unknown[]>();
    expect(Array.isArray(body)).toBe(true);
  });
});
```

## Anti-patterns

- **`experimentalDecorators: true`** — the old flag activates TS 4.x decorator semantics;
  combining it with stage-3 syntax causes silent misbehaviour. Remove it entirely.
- **`reflect-metadata` import** — the Workers runtime does not expose `Reflect.metadata`.
  Stage-3 decorators do not need it; importing it causes a runtime crash.
- **Decorating arrow-function properties** — stage-3 method decorators apply to prototype
  methods only. Arrow properties stored on `this` are not decorated; the `addInitializer`
  callback never fires on them.
- **Lazy controller instantiation per request** — instantiating the controller on every
  `fetch` call negates any startup optimisation. Build the router once in module scope or
  on first request and cache it.

## Gotchas

- `ctx.addInitializer` runs when the **instance** is created, not when the class is
  defined, so routes are registered on `this.constructor` during `new Ctor(env)`.
  If you introspect `getRoutes(Ctor)` before constructing an instance you get an empty
  array.
- `URLPattern` groups return `undefined` for unmatched optional segments; always guard
  with `params.id ?? ''` before passing to D1.
- esbuild must be run with `--target=es2022` or higher; `es2020` will attempt to downcompile
  decorators and produce incorrect output for stage-3 syntax.

## Verification

```bash
# Confirm esbuild emits native decorator syntax (no __decorate helper)
esbuild src/index.ts --bundle --platform=browser --target=es2022 --format=esm \
  | grep -c '__decorate'
# Expected: 0

# Run Vitest in Workers pool
pnpm vitest run --reporter=verbose

# Check route registration during wrangler dev startup
wrangler dev --local 2>&1 | grep 'Registered route'
```

## Related

- `vitest-workers-miniflare-testing-setup.md`
- `typescript-workers-env-interface-module-augmentation.md`
- `hono-rpc-client-type-generation-workers.md`
- `wrangler-dev-local-d1-r2-kv.md`

## Sources

- TC39 Decorators Proposal — https://github.com/tc39/proposal-decorators
- TypeScript 5.0 Release Notes (Stage-3 Decorators) — https://www.typescriptlang.org/docs/handbook/release-notes/typescript-5-0.html
- Cloudflare Workers URLPattern docs — https://developers.cloudflare.com/workers/runtime-apis/web-standards/#url-pattern-api
- esbuild decorator support — https://esbuild.github.io/content-types/#typescript-decorators

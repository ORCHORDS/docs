# Dependency Injection with Workers Bindings

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

A Cloudflare Worker handler imports `env.DB`, `env.KV`, and `env.QUEUE` directly. Unit testing the handler requires mocking the global `env` object, test isolation breaks when the handler constructs concrete classes internally, and replacing a D1 binding with an R2 binding demands changes throughout the codebase. Proper dependency injection (DI) solves all three problems without a framework.

---

## Context

Workers do not support a class instantiation lifecycle the way Node.js servers do. The `env` object is handed to the `fetch` or `queue` handler at request time, not at module initialisation time (module-level singletons are reused across requests but their bindings may differ per isolate). The solution is constructor injection: build the dependency graph inside the handler entrypoint and pass concrete implementations to domain/application objects through interfaces. No decorators, no IoC container — just TypeScript interfaces and factory functions.

---

## Define Infrastructure Interfaces (Domain Layer)

```typescript
// src/ports/Storage.ts
export interface KeyValueStore {
  get(key: string): Promise<string | null>;
  put(key: string, value: string, options?: { expirationTtl?: number }): Promise<void>;
  delete(key: string): Promise<void>;
}

export interface RelationalDB {
  queryOne<T>(sql: string, bindings: unknown[]): Promise<T | null>;
  queryAll<T>(sql: string, bindings: unknown[]): Promise<T[]>;
  execute(sql: string, bindings: unknown[]): Promise<{ rowsAffected: number }>;
}

export interface MessageQueue {
  send<T>(message: T): Promise<void>;
  sendBatch<T>(messages: T[]): Promise<void>;
}
```

---

## Adapter Implementations (Infrastructure Layer)

```typescript
// src/adapters/KVAdapter.ts
import type { KVNamespace } from "@cloudflare/workers-types";
import type { KeyValueStore } from "../ports/Storage";

export class KVAdapter implements KeyValueStore {
  constructor(private readonly kv: KVNamespace) {}

  get(key: string) { return this.kv.get(key); }
  put(key: string, value: string, opts?: { expirationTtl?: number }) {
    return this.kv.put(key, value, opts);
  }
  delete(key: string) { return this.kv.delete(key); }
}

// src/adapters/D1Adapter.ts
import type { D1Database } from "@cloudflare/workers-types";
import type { RelationalDB } from "../ports/Storage";

export class D1Adapter implements RelationalDB {
  constructor(private readonly db: D1Database) {}

  async queryOne<T>(sql: string, bindings: unknown[]): Promise<T | null> {
    return this.db.prepare(sql).bind(...bindings).first<T>();
  }

  async queryAll<T>(sql: string, bindings: unknown[]): Promise<T[]> {
    const result = await this.db.prepare(sql).bind(...bindings).all<T>();
    return result.results;
  }

  async execute(sql: string, bindings: unknown[]) {
    const result = await this.db.prepare(sql).bind(...bindings).run();
    return { rowsAffected: result.meta.changes ?? 0 };
  }
}
```

---

## Application Service with Constructor Injection

```typescript
// src/services/UserService.ts
import type { RelationalDB, KeyValueStore } from "../ports/Storage";

export class UserService {
  constructor(
    private readonly db: RelationalDB,
    private readonly cache: KeyValueStore
  ) {}

  async getUser(id: string): Promise<User | null> {
    const cached = await this.cache.get(`user:${id}`);
    if (cached) return JSON.parse(cached) as User;

    const user = await this.db.queryOne<User>(
      "SELECT id, email, name FROM users WHERE id = ?",
      [id]
    );
    if (user) {
      await this.cache.put(`user:${id}`, JSON.stringify(user), { expirationTtl: 300 });
    }
    return user;
  }

  async createUser(data: { email: string; name: string }): Promise<User> {
    const id = crypto.randomUUID();
    await this.db.execute(
      "INSERT INTO users (id, email, name) VALUES (?, ?, ?)",
      [id, data.email, data.name]
    );
    return { id, ...data };
  }
}
```

---

## Composition Root in the Worker Entry Point

```typescript
// src/index.ts — the ONLY place that imports env bindings directly
import { D1Adapter } from "./adapters/D1Adapter";
import { KVAdapter } from "./adapters/KVAdapter";
import { UserService } from "./services/UserService";
import { UserHandler } from "./handlers/UserHandler";

export interface Env {
  DB: D1Database;
  CACHE: KVNamespace;
  USER_QUEUE: Queue;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Composition root — build the graph once per request
    const db      = new D1Adapter(env.DB);
    const cache   = new KVAdapter(env.CACHE);
    const userSvc = new UserService(db, cache);
    const handler = new UserHandler(userSvc);

    return handler.handle(request);
  },
};
```

---

## Factory Helper for Shared Graphs

```typescript
// src/container.ts — avoids repeating the composition in multiple handlers
import type { Env } from "./index";
import { D1Adapter } from "./adapters/D1Adapter";
import { KVAdapter } from "./adapters/KVAdapter";
import { QueueAdapter } from "./adapters/QueueAdapter";
import { UserService } from "./services/UserService";
import { OrderService } from "./services/OrderService";

export interface Container {
  userService: UserService;
  orderService: OrderService;
}

export function buildContainer(env: Env): Container {
  const db    = new D1Adapter(env.DB);
  const cache = new KVAdapter(env.CACHE);
  const queue = new QueueAdapter(env.USER_QUEUE);

  return {
    userService:  new UserService(db, cache),
    orderService: new OrderService(db, queue),
  };
}

// In fetch handler:
// const { userService, orderService } = buildContainer(env);
```

---

## Unit Testing with In-Memory Fakes

```typescript
// test/fakes/InMemoryKV.ts
import type { KeyValueStore } from "../../src/ports/Storage";

export class InMemoryKV implements KeyValueStore {
  private store = new Map<string, { value: string; expiry?: number }>();

  async get(key: string): Promise<string | null> {
    const entry = this.store.get(key);
    if (!entry) return null;
    if (entry.expiry && Date.now() > entry.expiry) { this.store.delete(key); return null; }
    return entry.value;
  }

  async put(key: string, value: string, opts?: { expirationTtl?: number }): Promise<void> {
    this.store.set(key, {
      value,
      expiry: opts?.expirationTtl ? Date.now() + opts.expirationTtl * 1000 : undefined,
    });
  }

  async delete(key: string): Promise<void> { this.store.delete(key); }
}

// test/UserService.test.ts
import { describe, it, expect } from "vitest";
import { UserService } from "../src/services/UserService";
import { InMemoryKV } from "./fakes/InMemoryKV";
import { InMemoryDB } from "./fakes/InMemoryDB";

describe("UserService", () => {
  it("returns cached user on second call", async () => {
    const db    = new InMemoryDB();
    const cache = new InMemoryKV();
    const svc   = new UserService(db, cache);

    await svc.createUser({ email: "a@b.com", name: "Alice" });
    const u1 = await svc.getUser("...");  // populates cache
    const u2 = await svc.getUser("...");  // served from cache

    expect(db.queryCount).toBe(2); // insert + first getUser; second comes from cache
    expect(u1).toEqual(u2);
  });
});
```

---

## Anti-patterns

- **Accessing `env` deep in domain code**: importing bindings from a global or passing `env` directly into services leaks infrastructure coupling into the domain layer.
- **Module-level singleton services**: constructing services at module scope (outside the `fetch` handler) can cause bindings to bleed between requests on the same isolate in edge cases.
- **Using a DI framework with decorator metadata**: decorators require `experimentalDecorators` and runtime metadata; they add significant bundle overhead for Workers with tight size budgets.
- **Constructing adapters in tests**: tests that use real D1/KV adapters are integration tests — they must run against Miniflare, not in fast unit-test mode with Vitest.

---

## Gotchas

- **Cold start cost**: building the container on every `fetch` call adds microseconds; for deeply nested graphs, benchmark with `console.time` in Wrangler dev to check cost.
- **Shared mutable state across requests**: if a service holds mutable state (e.g., an internal cache map), that state is shared across concurrent requests on the same isolate — either make services stateless or use `WeakMap<Request, ...>` for request-scoped state.
- **TypeScript strict null checking**: `env.DB` is typed as `D1Database` not `D1Database | undefined`, but binding omissions at deploy time only surface at runtime; add a startup assertion (`if (!env.DB) throw new Error("DB binding missing")`) in the composition root.

---

## Verification

```bash
# Run unit tests (no Miniflare required — all fakes)
npx vitest run test/UserService.test.ts

# Run integration tests against local D1
npx wrangler dev --local
curl http://localhost:8787/users -X POST -d '{"email":"a@b.com","name":"Alice"}'
```

---

## Related

- `hexagonal-architecture.md` — ports-and-adapters overview; this article is the Workers-specific implementation
- `application-services.md` — application service layer above domain services
- `domain-service-pattern-workers-d1.md` — injecting repositories into domain services
- `repository-pattern-ddd.md` — repository interface contracts
- `unit-of-work-d1-workers.md` — batching multiple adapter calls in a single transaction

---

## Sources

- Seemann, M. (2011). *Dependency Injection in .NET*. Manning. Ch. 3 — Pure DI
- Cloudflare Workers — module worker lifecycle and isolate reuse documentation
- Vitest documentation — in-process unit testing for Workers

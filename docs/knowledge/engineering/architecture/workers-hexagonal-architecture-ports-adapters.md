# Hexagonal (Ports & Adapters) Architecture in Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your Cloudflare Worker business logic is tightly coupled to `KVNamespace`, `D1Database`, and `Queue` bindings. Unit tests require a full Workers runtime, integration tests are slow, and swapping storage backends means rewriting core logic. You need a way to keep domain code pure and independently testable.

## Context

Hexagonal Architecture (Alistair Cockburn, 2005) separates an application into three zones:

- **Domain core** – pure business logic, no I/O, no framework imports.
- **Inbound ports** – interfaces the outside world uses to drive the core (HTTP, cron).
- **Outbound ports** – interfaces the core uses to reach infrastructure (KV, D1, Queues, external APIs).

Adapters implement the ports. In a Workers context the runtime injects real adapters at request time; tests inject in-memory fakes.

## Solution

### 1. Define outbound port interfaces (domain layer)

```typescript
// src/domain/ports.ts

export interface UserRepository {
  findById(id: string): Promise<User | null>;
  save(user: User): Promise<void>;
  delete(id: string): Promise<void>;
}

export interface EventPublisher {
  publish(event: DomainEvent): Promise<void>;
}

export interface CacheStore {
  get<T>(key: string): Promise<T | null>;
  set<T>(key: string, value: T, ttlSeconds: number): Promise<void>;
  delete(key: string): Promise<void>;
}

export interface User {
  id: string;
  email: string;
  plan: 'free' | 'pro' | 'enterprise';
  createdAt: number;
}

export interface DomainEvent {
  type: string;
  payload: Record<string, unknown>;
  occurredAt: number;
}
```

### 2. Pure domain service (no Workers imports)

```typescript
// src/domain/user-service.ts
import type { UserRepository, EventPublisher, CacheStore, User } from './ports';

export class UserService {
  constructor(
    private readonly users: UserRepository,
    private readonly events: EventPublisher,
    private readonly cache: CacheStore,
  ) {}

  async getUser(id: string): Promise<User | null> {
    const cached = await this.cache.get<User>(`user:${id}`);
    if (cached) return cached;

    const user = await this.users.findById(id);
    if (user) await this.cache.set(`user:${id}`, user, 300);
    return user;
  }

  async upgradeUser(id: string, newPlan: User['plan']): Promise<void> {
    const user = await this.users.findById(id);
    if (!user) throw new Error(`User ${id} not found`);
    if (user.plan === newPlan) return;

    const updated: User = { ...user, plan: newPlan };
    await this.users.save(updated);
    await this.cache.delete(`user:${id}`);
    await this.events.publish({
      type: 'user.plan_changed',
      payload: { userId: id, from: user.plan, to: newPlan },
      occurredAt: Date.now(),
    });
  }

  async deleteUser(id: string): Promise<void> {
    await this.users.delete(id);
    await this.cache.delete(`user:${id}`);
    await this.events.publish({
      type: 'user.deleted',
      payload: { userId: id },
      occurredAt: Date.now(),
    });
  }
}
```

### 3. Outbound adapter – D1 (UserRepository)

```typescript
// src/adapters/d1-user-repository.ts
import type { UserRepository, User } from '../domain/ports';

export class D1UserRepository implements UserRepository {
  constructor(private readonly db: D1Database) {}

  async findById(id: string): Promise<User | null> {
    const row = await this.db
      .prepare('SELECT id, email, plan, created_at FROM users WHERE id = ?')
      .bind(id)
      .first<{ id: string; email: string; plan: string; created_at: number }>();

    if (!row) return null;
    return {
      id: row.id,
      email: row.email,
      plan: row.plan as User['plan'],
      createdAt: row.created_at,
    };
  }

  async save(user: User): Promise<void> {
    await this.db
      .prepare(
        `INSERT INTO users (id, email, plan, created_at)
         VALUES (?, ?, ?, ?)
         ON CONFLICT(id) DO UPDATE SET email = excluded.email, plan = excluded.plan`,
      )
      .bind(user.id, user.email, user.plan, user.createdAt)
      .run();
  }

  async delete(id: string): Promise<void> {
    await this.db.prepare('DELETE FROM users WHERE id = ?').bind(id).run();
  }
}
```

### 4. Outbound adapter – KV (CacheStore)

```typescript
// src/adapters/kv-cache-store.ts
import type { CacheStore } from '../domain/ports';

export class KVCacheStore implements CacheStore {
  constructor(private readonly kv: KVNamespace) {}

  async get<T>(key: string): Promise<T | null> {
    return this.kv.get<T>(key, 'json');
  }

  async set<T>(key: string, value: T, ttlSeconds: number): Promise<void> {
    await this.kv.put(key, JSON.stringify(value), { expirationTtl: ttlSeconds });
  }

  async delete(key: string): Promise<void> {
    await this.kv.delete(key);
  }
}
```

### 5. Outbound adapter – Queue (EventPublisher)

```typescript
// src/adapters/queue-event-publisher.ts
import type { EventPublisher, DomainEvent } from '../domain/ports';

export class QueueEventPublisher implements EventPublisher {
  constructor(private readonly queue: Queue<DomainEvent>) {}

  async publish(event: DomainEvent): Promise<void> {
    await this.queue.send(event);
  }
}
```

### 6. Inbound adapter – HTTP handler (assembles the hexagon)

```typescript
// src/adapters/http-handler.ts
import { UserService } from '../domain/user-service';
import { D1UserRepository } from './d1-user-repository';
import { KVCacheStore } from './kv-cache-store';
import { QueueEventPublisher } from './queue-event-publisher';
import type { DomainEvent } from '../domain/ports';

export interface Env {
  DB: D1Database;
  CACHE: KVNamespace;
  EVENTS: Queue<DomainEvent>;
}

function buildService(env: Env): UserService {
  return new UserService(
    new D1UserRepository(env.DB),
    new QueueEventPublisher(env.EVENTS),
    new KVCacheStore(env.CACHE),
  );
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const service = buildService(env);

    // GET /users/:id
    const getMatch = url.pathname.match(/^\/users\/([^/]+)$/);
    if (request.method === 'GET' && getMatch) {
      const user = await service.getUser(getMatch[1]);
      if (!user) return new Response('Not Found', { status: 404 });
      return Response.json(user);
    }

    // PATCH /path/to/plan
    const upgradeMatch = url.pathname.match(/^\/users\/([^/]+)\/plan$/);
    if (request.method === 'PATCH' && upgradeMatch) {
      const body = await request.json<{ plan: string }>();
      await service.upgradeUser(upgradeMatch[1], body.plan as any);
      return new Response(null, { status: 204 });
    }

    // DELETE /users/:id
    const deleteMatch = url.pathname.match(/^\/users\/([^/]+)$/);
    if (request.method === 'DELETE' && deleteMatch) {
      await service.deleteUser(deleteMatch[1]);
      return new Response(null, { status: 204 });
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

### 7. In-memory adapters for unit tests

```typescript
// src/adapters/in-memory.ts
import type { UserRepository, CacheStore, EventPublisher, User, DomainEvent } from '../domain/ports';

export class InMemoryUserRepository implements UserRepository {
  private store = new Map<string, User>();

  async findById(id: string): Promise<User | null> {
    return this.store.get(id) ?? null;
  }

  async save(user: User): Promise<void> {
    this.store.set(user.id, { ...user });
  }

  async delete(id: string): Promise<void> {
    this.store.delete(id);
  }

  seed(users: User[]): void {
    users.forEach(u => this.store.set(u.id, u));
  }
}

export class InMemoryCacheStore implements CacheStore {
  private store = new Map<string, { value: unknown; expiresAt: number }>();

  async get<T>(key: string): Promise<T | null> {
    const entry = this.store.get(key);
    if (!entry || Date.now() > entry.expiresAt) return null;
    return entry.value as T;
  }

  async set<T>(key: string, value: T, ttlSeconds: number): Promise<void> {
    this.store.set(key, { value, expiresAt: Date.now() + ttlSeconds * 1000 });
  }

  async delete(key: string): Promise<void> {
    this.store.delete(key);
  }
}

export class InMemoryEventPublisher implements EventPublisher {
  readonly published: DomainEvent[] = [];

  async publish(event: DomainEvent): Promise<void> {
    this.published.push(event);
  }
}
```

### 8. Unit test (no Workers runtime required)

```typescript
// src/domain/user-service.test.ts
import { UserService } from './user-service';
import {
  InMemoryUserRepository,
  InMemoryCacheStore,
  InMemoryEventPublisher,
} from '../adapters/in-memory';
import type { User } from './ports';

const ALICE: User = { id: 'u1', email: 'alice@example.com', plan: 'free', createdAt: 1000 };

function setup() {
  const users = new InMemoryUserRepository();
  const cache = new InMemoryCacheStore();
  const events = new InMemoryEventPublisher();
  const service = new UserService(users, events, cache);
  return { users, cache, events, service };
}

test('upgradeUser emits plan_changed event', async () => {
  const { users, events, service } = setup();
  users.seed([ALICE]);

  await service.upgradeUser('u1', 'pro');

  expect(events.published).toHaveLength(1);
  expect(events.published[0].type).toBe('user.plan_changed');
  expect(events.published[0].payload).toMatchObject({ from: 'free', to: 'pro' });
});

test('getUser returns cached value on second call', async () => {
  const { users, cache, service } = setup();
  users.seed([ALICE]);

  await service.getUser('u1'); // populates cache
  await users.delete('u1');   // remove from store — cache should still serve it
  const result = await service.getUser('u1');

  expect(result).not.toBeNull();
  expect(result!.email).toBe('alice@example.com');
});
```

## Implementation Details

- **Composition root** lives in the inbound adapter (`http-handler.ts`). Only this file imports from both domain and infrastructure layers.
- **Port interfaces** are TypeScript `interface` types, not abstract classes — zero runtime cost.
- **One service instance per request** is fine in Workers (no shared heap between requests on the same isolate in V8 sandbox terms), but you can hoist read-only adapter instances to module scope if they hold no per-request state.
- **wrangler.toml** bindings map directly to `Env` properties; TypeScript types come from `@cloudflare/workers-types`.

```toml
# wrangler.toml
[[d1_databases]]
binding = "DB"
database_name = "myapp"
database_id  = "<uuid>"

[[kv_namespaces]]
binding = "CACHE"
id = "<uuid>"

[[queues.producers]]
binding  = "EVENTS"
queue    = "domain-events"
```

## Anti-patterns

- **Importing `cloudflare:workers` inside the domain** — breaks portability and forces miniflare for every unit test.
- **Fat adapters with business logic** — e.g. computing derived fields inside `D1UserRepository`. Adapters only translate between protocol and domain types.
- **Singleton service with shared mutable state** — Workers isolates can be reused across requests; module-scope state persists. Keep domain services stateless or treat module-scope state as a cache with explicit invalidation.
- **Using `any` on port interfaces** — defeats the compile-time contract; always type `DomainEvent` payload generically or with discriminated unions.

## Gotchas

- `D1Database.prepare().first()` returns `null` when no row matches, not `undefined`. Guard with `?? null` or `=== null` checks.
- `KVNamespace.get('key', 'json')` returns `null` on miss AND on parse failure — wrap in a try/catch if you want to distinguish the two.
- Queue `send()` is best-effort; the consumer may receive the message more than once. Make domain event handlers idempotent.
- `wrangler dev` with `--local` runs D1 via better-sqlite3 — schema must be compatible with SQLite (no `RETURNING` before D1 supported it).

## Verification

```bash
# Unit tests (no network, no Workers runtime)
npx vitest run src/domain/

# Integration tests against local bindings
npx wrangler dev --local &
curl -s http://localhost:8787/users/u1

# Type-check
npx tsc --noEmit
```

## Related

- `workers-cqrs-command-query-separation.md`
- `workers-event-driven-webhooks-queues.md`
- `workers-multi-tenant-isolation-durable-objects.md`

## Sources

- Alistair Cockburn, "Hexagonal Architecture" (2005) — https://alistair.cockburn.us/hexagonal-architecture/
- Cloudflare Workers D1 docs — https://developers.cloudflare.com/d1/
- Cloudflare Queues docs — https://developers.cloudflare.com/queues/
- Cloudflare KV docs — https://developers.cloudflare.com/kv/

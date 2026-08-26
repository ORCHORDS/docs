# Hexagonal Architecture (Ports & Adapters) in TypeScript Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Worker handlers that reach directly into `env.DB` or `env.KV` become impossible to unit-test without a live D1 binding and hard to swap when storage requirements change. You need to push infrastructure concerns to the boundary of your application so the core domain remains pure TypeScript.

---

## Context
Hexagonal architecture (also called ports & adapters) defines the domain at the centre and wraps it with ports — interfaces the domain depends on — and adapters that implement those ports using real infrastructure. In a Cloudflare Workers context `env` acts as the dependency-injection container: the Worker entry point constructs concrete adapters from `env` bindings and passes them into domain services. The domain service (`UserService`) only ever imports the port interface, never a concrete adapter, keeping it testable with a plain in-memory mock.

---

## Section 1 — Wrangler Config

```toml
# wrangler.toml
name = "hexagonal-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[d1_databases]]
binding = "DB"
database_name = "hex-db"
database_id = "<your-d1-database-id>"

[[kv_namespaces]]
binding = "USER_CACHE"
id = "<your-kv-namespace-id>"
```

```sql
-- migrations/0001_users.sql
CREATE TABLE IF NOT EXISTS users (
  id         TEXT PRIMARY KEY,
  email      TEXT UNIQUE NOT NULL,
  name       TEXT NOT NULL,
  created_at TEXT NOT NULL
);
```

---

## Section 2 — Port, Adapters, and Domain Service

```typescript
// src/domain/user.ts
export interface User {
  id: string;
  email: string;
  name: string;
  createdAt: string;
}

// src/ports/user-repository.ts  (the PORT — pure interface, no imports from infra)
export interface UserRepository {
  findById(id: string): Promise<User | null>;
  findByEmail(email: string): Promise<User | null>;
  save(user: User): Promise<void>;
  delete(id: string): Promise<void>;
}

// src/adapters/d1-user-repository.ts  (adapter for D1)
import type { D1Database } from '@cloudflare/workers-types';
import type { UserRepository } from '../ports/user-repository';
import type { User } from '../domain/user';

export class D1UserRepository implements UserRepository {
  constructor(private readonly db: D1Database) {}

  async findById(id: string): Promise<User | null> {
    const row = await this.db
      .prepare('SELECT * FROM users WHERE id = ?')
      .bind(id)
      .first<User>();
    return row ?? null;
  }

  async findByEmail(email: string): Promise<User | null> {
    const row = await this.db
      .prepare('SELECT * FROM users WHERE email = ?')
      .bind(email)
      .first<User>();
    return row ?? null;
  }

  async save(user: User): Promise<void> {
    await this.db
      .prepare(
        `INSERT INTO users (id, email, name, created_at)
         VALUES (?, ?, ?, ?)
         ON CONFLICT(id) DO UPDATE SET email=excluded.email, name=excluded.name`
      )
      .bind(user.id, user.email, user.name, user.createdAt)
      .run();
  }

  async delete(id: string): Promise<void> {
    await this.db.prepare('DELETE FROM users WHERE id = ?').bind(id).run();
  }
}

// src/adapters/kv-user-repository.ts  (adapter for KV — read-through cache layer)
import type { KVNamespace } from '@cloudflare/workers-types';
import type { UserRepository } from '../ports/user-repository';
import type { User } from '../domain/user';

export class KVUserRepository implements UserRepository {
  constructor(
    private readonly kv: KVNamespace,
    private readonly fallback: UserRepository
  ) {}

  async findById(id: string): Promise<User | null> {
    const cached = await this.kv.get<User>(`user:${id}`, 'json');
    if (cached) return cached;
    const user = await this.fallback.findById(id);
    if (user) await this.kv.put(`user:${id}`, JSON.stringify(user), { expirationTtl: 300 });
    return user;
  }

  async findByEmail(email: string): Promise<User | null> {
    return this.fallback.findByEmail(email);
  }

  async save(user: User): Promise<void> {
    await this.fallback.save(user);
    await this.kv.put(`user:${user.id}`, JSON.stringify(user), { expirationTtl: 300 });
  }

  async delete(id: string): Promise<void> {
    await this.fallback.delete(id);
    await this.kv.delete(`user:${id}`);
  }
}

// src/domain/user-service.ts  (DOMAIN — depends only on the port interface)
import { randomUUID } from 'crypto';
import type { UserRepository } from '../ports/user-repository';
import type { User } from './user';

export class UserService {
  constructor(private readonly users: UserRepository) {}

  async register(email: string, name: string): Promise<User> {
    const existing = await this.users.findByEmail(email);
    if (existing) throw new Error(`Email already registered: ${email}`);

    const user: User = {
      id: randomUUID(),
      email,
      name,
      createdAt: new Date().toISOString(),
    };
    await this.users.save(user);
    return user;
  }

  async getProfile(id: string): Promise<User> {
    const user = await this.users.findById(id);
    if (!user) throw new Error(`User not found: ${id}`);
    return user;
  }

  async deactivate(id: string): Promise<void> {
    const user = await this.users.findById(id);
    if (!user) throw new Error(`User not found: ${id}`);
    await this.users.delete(id);
  }
}

// src/index.ts  (composition root — the only file that knows about concrete adapters)
import { D1UserRepository } from './adapters/d1-user-repository';
import { KVUserRepository } from './adapters/kv-user-repository';
import { UserService } from './domain/user-service';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Dependency injection via env (the DI container in Workers)
    const d1Repo = new D1UserRepository(env.DB);
    const cachedRepo = new KVUserRepository(env.USER_CACHE, d1Repo);
    const userService = new UserService(cachedRepo);

    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/users') {
      const { email, name } = await request.json<{ email: string; name: string }>();
      const user = await userService.register(email, name);
      return Response.json(user, { status: 201 });
    }

    const match = url.pathname.match(/^\/users\/([\w-]+)$/);
    if (match && request.method === 'GET') {
      const user = await userService.getProfile(match[1]);
      return Response.json(user);
    }

    return new Response('Not found', { status: 404 });
  },
};
```

---

## Section 3 — Unit Testing with a Mock Adapter

```typescript
// tests/user-service.test.ts
import { describe, it, expect, beforeEach } from 'vitest';
import type { UserRepository } from '../src/ports/user-repository';
import type { User } from '../src/domain/user';
import { UserService } from '../src/domain/user-service';

// In-memory adapter — no Workers runtime needed
class InMemoryUserRepository implements UserRepository {
  private store = new Map<string, User>();

  async findById(id: string): Promise<User | null> {
    return this.store.get(id) ?? null;
  }

  async findByEmail(email: string): Promise<User | null> {
    for (const user of this.store.values()) {
      if (user.email === email) return user;
    }
    return null;
  }

  async save(user: User): Promise<void> {
    this.store.set(user.id, user);
  }

  async delete(id: string): Promise<void> {
    this.store.delete(id);
  }
}

describe('UserService', () => {
  let repo: InMemoryUserRepository;
  let service: UserService;

  beforeEach(() => {
    repo = new InMemoryUserRepository();
    service = new UserService(repo);
  });

  it('registers a new user', async () => {
    const user = await service.register('alice@example.com', 'Alice');
    expect(user.email).toBe('alice@example.com');
    expect(user.id).toBeTruthy();
  });

  it('throws when email already exists', async () => {
    await service.register('bob@example.com', 'Bob');
    await expect(service.register('bob@example.com', 'Bob 2')).rejects.toThrow(
      'Email already registered'
    );
  });

  it('retrieves an existing profile', async () => {
    const created = await service.register('carol@example.com', 'Carol');
    const fetched = await service.getProfile(created.id);
    expect(fetched).toEqual(created);
  });

  it('throws when user not found', async () => {
    await expect(service.getProfile('missing-id')).rejects.toThrow('User not found');
  });
});
```

---

## Anti-patterns
- **Importing `env.DB` directly inside the domain service** — couples domain logic to infra; the service becomes untestable without a real D1 binding.
- **A single repository class that knows about both D1 and KV** — violates single responsibility; use the decorator/wrapper pattern as shown with `KVUserRepository`.
- **Constructing adapters inside the domain** — the domain must not know how to build its own dependencies.

---

## Gotchas
- `KVUserRepository.findByEmail` skips the cache because KV is keyed by id; secondary indexes in KV require an extra key like `email:<hash> → user-id`.
- D1's `first()` returns `null` (not `undefined`) when no row is found — `?? null` is redundant but makes TypeScript happy without extra type assertions.
- In local dev (`wrangler dev`), KV TTL is not enforced — test cache expiry in a preview environment.

---

## Verification

```bash
# Run unit tests (no runtime required)
npx vitest run tests/user-service.test.ts

# Apply migration
wrangler d1 execute hex-db --file=migrations/0001_users.sql

# Register user
curl -X POST https://<worker>.workers.dev/users \
  -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.com","name":"Alice"}'

# Fetch profile
curl https://<worker>.workers.dev/users/<returned-id>
```

---

## Related
- `workers-cqrs-d1-read-write-separation.md`
- `workers-clean-architecture-use-cases.md`
- `workers-actor-model-durable-objects.md`

---

## Sources
- Alistair Cockburn — Hexagonal Architecture — https://alistair.cockburn.us/hexagonal-architecture/
- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- Cloudflare KV documentation — https://developers.cloudflare.com/kv/

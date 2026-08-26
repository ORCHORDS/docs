# Repository Pattern Abstracting D1 Access in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Domain logic directly calls `env.DB.prepare(...)` throughout handler code. Switching databases,
adding query caching, or writing unit tests requires touching every handler. Queries become
scattered, untestable, and tightly coupled to Cloudflare D1's API surface.

## Context

Cloudflare Workers expose a D1 binding (`env.DB`) with a low-level `prepare → bind → run/all/first`
interface. The Repository pattern wraps this behind a domain-facing interface so that:

- Handlers depend on an abstraction, not a concrete D1 binding
- An in-memory stub can substitute in unit tests (no Miniflare required)
- Query logic lives in one cohesive class rather than scattered across handlers
- Future migrations (e.g. to Hyperdrive-backed Postgres) touch only the repository

---

## Section 1 — Define the Repository Interface

Start with a pure TypeScript interface that captures what the domain needs, with no D1 types
leaking through.

```typescript
// src/domain/repositories/IUserRepository.ts

export interface User {
  id: string;
  email: string;
  displayName: string;
  createdAt: Date;
}

export interface CreateUserInput {
  id: string;
  email: string;
  displayName: string;
}

export interface IUserRepository {
  findById(id: string): Promise<User | null>;
  findByEmail(email: string): Promise<User | null>;
  listAll(limit?: number, offset?: number): Promise<User[]>;
  create(input: CreateUserInput): Promise<User>;
  update(id: string, patch: Partial<Pick<User, 'email' | 'displayName'>>): Promise<User | null>;
  delete(id: string): Promise<boolean>;
}
```

---

## Section 2 — D1 Implementation

The concrete implementation translates domain calls to prepared D1 statements. All D1 types
stay confined to this file.

```typescript
// src/infrastructure/repositories/D1UserRepository.ts

import type { D1Database } from '@cloudflare/workers-types';
import type { User, CreateUserInput, IUserRepository } from '../../domain/repositories/IUserRepository';

interface D1UserRow {
  id: string;
  email: string;
  display_name: string;
  created_at: string; // ISO string stored as TEXT
}

function rowToUser(row: D1UserRow): User {
  return {
    id: row.id,
    email: row.email,
    displayName: row.display_name,
    createdAt: new Date(row.created_at),
  };
}

export class D1UserRepository implements IUserRepository {
  constructor(private readonly db: D1Database) {}

  async findById(id: string): Promise<User | null> {
    const row = await this.db
      .prepare('SELECT id, email, display_name, created_at FROM users WHERE id = ?1')
      .bind(id)
      .first<D1UserRow>();
    return row ? rowToUser(row) : null;
  }

  async findByEmail(email: string): Promise<User | null> {
    const row = await this.db
      .prepare('SELECT id, email, display_name, created_at FROM users WHERE email = ?1')
      .bind(email)
      .first<D1UserRow>();
    return row ? rowToUser(row) : null;
  }

  async listAll(limit = 20, offset = 0): Promise<User[]> {
    const { results } = await this.db
      .prepare(
        'SELECT id, email, display_name, created_at FROM users ORDER BY created_at DESC LIMIT ?1 OFFSET ?2'
      )
      .bind(limit, offset)
      .all<D1UserRow>();
    return results.map(rowToUser);
  }

  async create(input: CreateUserInput): Promise<User> {
    const now = new Date().toISOString();
    await this.db
      .prepare(
        'INSERT INTO users (id, email, display_name, created_at) VALUES (?1, ?2, ?3, ?4)'
      )
      .bind(input.id, input.email, input.displayName, now)
      .run();
    return { ...input, createdAt: new Date(now) };
  }

  async update(
    id: string,
    patch: Partial<Pick<User, 'email' | 'displayName'>>
  ): Promise<User | null> {
    const existing = await this.findById(id);
    if (!existing) return null;

    const email = patch.email ?? existing.email;
    const displayName = patch.displayName ?? existing.displayName;

    await this.db
      .prepare('UPDATE users SET email = ?1, display_name = ?2 WHERE id = ?3')
      .bind(email, displayName, id)
      .run();

    return { ...existing, email, displayName };
  }

  async delete(id: string): Promise<boolean> {
    const result = await this.db
      .prepare('DELETE FROM users WHERE id = ?1')
      .bind(id)
      .run();
    return (result.meta.changes ?? 0) > 0;
  }
}
```

---

## Section 3 — In-Memory Mock for Tests

The mock satisfies `IUserRepository` with a plain `Map`, allowing fast, dependency-free unit
tests that run with plain `vitest` — no Miniflare, no D1 binding needed.

```typescript
// src/infrastructure/repositories/InMemoryUserRepository.ts

import type { User, CreateUserInput, IUserRepository } from '../../domain/repositories/IUserRepository';

export class InMemoryUserRepository implements IUserRepository {
  private store = new Map<string, User>();

  seed(users: User[]): void {
    for (const u of users) this.store.set(u.id, u);
  }

  async findById(id: string): Promise<User | null> {
    return this.store.get(id) ?? null;
  }

  async findByEmail(email: string): Promise<User | null> {
    for (const u of this.store.values()) {
      if (u.email === email) return u;
    }
    return null;
  }

  async listAll(limit = 20, offset = 0): Promise<User[]> {
    return [...this.store.values()]
      .sort((a, b) => b.createdAt.getTime() - a.createdAt.getTime())
      .slice(offset, offset + limit);
  }

  async create(input: CreateUserInput): Promise<User> {
    const user: User = { ...input, createdAt: new Date() };
    this.store.set(user.id, user);
    return user;
  }

  async update(
    id: string,
    patch: Partial<Pick<User, 'email' | 'displayName'>>
  ): Promise<User | null> {
    const existing = this.store.get(id);
    if (!existing) return null;
    const updated = { ...existing, ...patch };
    this.store.set(id, updated);
    return updated;
  }

  async delete(id: string): Promise<boolean> {
    return this.store.delete(id);
  }
}
```

---

## Section 4 — Dependency Injection in the Worker Handler

Repositories are constructed once per request from `env`, keeping the handler ignorant of D1.

```typescript
// src/handlers/userHandler.ts

import { D1UserRepository } from '../infrastructure/repositories/D1UserRepository';
import type { IUserRepository } from '../domain/repositories/IUserRepository';

interface Env {
  DB: D1Database;
}

// Domain service — depends only on the interface
async function getUserOrThrow(
  repo: IUserRepository,
  id: string
) {
  const user = await repo.findById(id);
  if (!user) throw new Response('Not Found', { status: 404 });
  return user;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const repo: IUserRepository = new D1UserRepository(env.DB);

    const url = new URL(request.url);
    const id = url.searchParams.get('id');
    if (!id) return new Response('Bad Request', { status: 400 });

    try {
      const user = await getUserOrThrow(repo, id);
      return Response.json(user);
    } catch (e) {
      if (e instanceof Response) return e;
      throw e;
    }
  },
};
```

---

## Anti-patterns

- **Leaking `D1Database` into domain services** — the domain must never import `@cloudflare/workers-types`.
- **One repository per table** anti-pattern confusion — repositories are per *aggregate root*, not per table. A `UserRepository` may join several tables internally.
- **Returning raw D1 rows** — always map to domain types before returning; SQL column names are an infrastructure detail.
- **Skipping the interface** — without it you cannot substitute the mock, negating the pattern's main benefit.

## Gotchas

- D1's `.first<T>()` returns `null` (not `undefined`) when no row matches — match that in your mock.
- `result.meta.changes` can be `undefined` on some D1 versions; default to `0`.
- Prepared statements are not reused across requests in Workers (no persistent connection), so there is no pool to manage.
- D1 column names use `snake_case` by convention; map to `camelCase` in the adapter, not in application code.

## Verification

```bash
# Run unit tests with the in-memory mock — no Wrangler needed
npx vitest run src/domain

# Run integration tests against a local D1 database
npx wrangler d1 execute DB --local --file=migrations/001_create_users.sql
npx vitest run src/infrastructure
```

## Related

- `workers-unit-of-work-d1-batch.md` — batching multiple repository writes atomically
- `workers-value-object-pattern-typescript.md` — typed `UserId`, `Email` values used by repositories
- `workers-anti-corruption-layer-legacy.md` — repositories that translate external API responses

## Sources

- [Cloudflare D1 documentation](https://developers.cloudflare.com/d1/)
- Evans, E. (2003). *Domain-Driven Design*. Addison-Wesley. Chapter 6: The Life Cycle of a Domain Object.
- Fowler, M. (2002). *Patterns of Enterprise Application Architecture*. Addison-Wesley. Repository pattern.

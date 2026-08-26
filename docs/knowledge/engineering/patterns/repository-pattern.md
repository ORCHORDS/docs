# repository-pattern

**Issue:** Abstract data access from business logic
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your handler has 50 lines of D1 SQL queries mixed with business
logic. You want to test the business logic without a real D1.
You can't — the SQL is intertwined. Refactoring is hard.

## Root cause
**The handler knows too much about the data layer.** It knows
the table names, the column types, the SQL syntax. To test the
business logic, you need a real (or mocked) D1.

**Source:** Martin Fowler — Repository:
https://martinfowler.com/eaaCatalog/repository.html

> "A Repository mediates between the domain and data mapping
> layers using a collection-like interface for accessing domain
> objects."

## Fix

### The pattern

```ts
// The interface
interface UserRepository {
  getById(id: string): Promise<User | null>;
  getByEmail(tenantId: string, email: string): Promise<User | null>;
  list(tenantId: string, opts: { limit: number; offset: number }): Promise<User[]>;
  create(user: NewUser): Promise<User>;
  update(id: string, changes: Partial<User>): Promise<User>;
  delete(id: string): Promise<void>;
}

// The D1 implementation
class D1UserRepository implements UserRepository {
  constructor(private db: D1Database) {}

  async getById(id: string): Promise<User | null> {
    return this.db.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first<User>();
  }
  // ... etc
}

// The in-memory implementation (for tests)
class InMemoryUserRepository implements UserRepository {
  private users = new Map<string, User>();
  // ... etc
}

// The handler
async function createUser(req: Request, repo: UserRepository, ctx: McContext): Promise<Response> {
  const data = await req.json() as NewUser;
  if (!data.email || !data.displayName) return new Response('Bad Request', { status: 400 });
  const existing = await repo.getByEmail(ctx.tenant.id, data.email);
  if (existing) return new Response('Conflict', { status: 409 });
  const user = await repo.create({ ...data, tenantId: ctx.tenant.id });
  return new Response(JSON.stringify(user), { status: 201 });
}
```

The handler is pure logic. The repository is data access. Tests
can use the in-memory repo. Production uses the D1 repo.

## When to use

✅ Use repositories when:
- **The handler is non-trivial** (more than 5 lines of logic)
- **You want to test the handler in isolation** (no real DB)
- **You might switch data stores** (D1 → Postgres, or add
  caching)
- **Multiple data sources** (e.g. user in D1, posts in another
  DB)

❌ Don't use repositories when:
- **The handler is trivial** (1-2 lines of SQL)
- **The query is one-off** (a complex report that's never
  reused)
- **Performance matters more than abstraction** (a complex
  query that the optimizer handles better in raw SQL)

## Folder structure

For a TypeScript project:
```
functions/api/mc/users/
├── [[path]].ts             # the route
├── _handlers.ts            # business logic
├── _repository.ts          # the repository interface
├── _repository.d1.ts       # the D1 implementation
└── _repository.memory.ts   # the in-memory test implementation
```

The handler imports the interface; the route file picks the
implementation based on env.

## Verification
- **Test:** `test/users-repository.test.ts` — handler logic is
  testable with the in-memory repo; D1 repo has its own tests
  for SQL correctness
- **Live:** Production uses the D1 repo; no behavioral change
- **Audit:** Review of repository methods for N+1 queries,
  missing indexes, etc.

## Gotchas
- **The repository pattern adds boilerplate.** For simple CRUD,
  it's overkill. Use it for complex domain logic only.
- **The interface is a contract.** Adding a new method is a
  breaking change for all implementations. Update tests too.
- **Don't expose the D1Database through the interface.** If the
  handler needs to do a custom query, add a method to the repo
  instead of `repo.db.prepare(...)`.
- **For D1 specifically**, the bundler has issues with raw SQL
  in some patterns. The repo pattern makes it easier to centralize
  SQL in one place.
- **Repositories don't replace transactions.** If you need
  multi-row atomicity, the repo's `create` and `update` methods
  are separate; they can't be in the same transaction. Add an
  `transaction(fn)` method or use a Unit of Work pattern.

## Related
- `per-tenant-durable-object.md` (an alternative for
  single-tenant consistency)
- `d1-batch-bundler-bug.md` (D1-specific gotcha)
- Martin Fowler: https://martinfowler.com/eaaCatalog/repository.html
- Unit of Work: https://martinfowler.com/eaaCatalog/unitOfWork.html

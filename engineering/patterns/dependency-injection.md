# dependency-injection

**Issue:** DI in CF Workers — manual, no frameworks
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your CF Worker calls D1, R2, KV, vendor APIs directly.
Your tests are all integration tests. You can't test a
handler without setting up D1 + R2 + KV + the vendor API.
A unit test takes 30 seconds to set up. You don't write
unit tests.

## Root cause
**Hard-coded dependencies are hard to test.** A function
that calls `env.DB!.prepare(...)` directly is tied to D1.
A function that takes a `db` parameter is testable.

**Source:** Martin Fowler — Inversion of Control:
https://martinfowler.com/articles/injection.html

## The pattern: constructor injection

```ts
// ❌ Hard-coded
class UserService {
  async getById(id: string): Promise<User> {
    return env.DB!.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first();
  }
}

// ✅ Constructor injection
class UserService {
  constructor(private db: D1Database) {}

  async getById(id: string): Promise<User> {
    return this.db.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first();
  }
}

// Usage
const userService = new UserService(env.DB!);
const user = await userService.getById('u_123');
```

The `db` is passed in. In tests, you pass a mock DB.

## The pattern: request-scoped

For a CF Worker, the dependencies are per-request. Build a
"context" object:

```ts
interface AppContext {
  env: Env;
  requestId: string;
  tenantId?: string;
  userId?: string;
}

function buildContext(request: Request, env: Env): AppContext {
  return {
    env,
    requestId: crypto.randomUUID(),
    // ... populate from request headers, JWT, etc.
  };
}

async function handleRequest(request: Request, env: Env): Promise<Response> {
  const ctx = buildContext(request, env);
  const userService = new UserService(ctx.env.DB!);
  const result = await userService.getById('u_123');
  return new Response(JSON.stringify(result));
}
```

## The pattern: factories

For complex dependencies (e.g. a service that depends on
multiple DBs), use a factory:

```ts
class UserService {
  constructor(
    private db: D1Database,
    private cache: KVNamespace,
    private metrics: MetricsService,
  ) {}
}

function createUserService(ctx: AppContext): UserService {
  return new UserService(
    ctx.env.DB!,
    ctx.env.KV!,
    createMetricsService(ctx),
  );
}
```

## The pattern: interface + impl

For maximum testability, use an interface:

```ts
// Define an interface
interface UserRepository {
  getById(id: string): Promise<User | null>;
  create(input: UserInput): Promise<User>;
  // ...
}

// One implementation (D1)
class D1UserRepository implements UserRepository {
  constructor(private db: D1Database) {}

  async getById(id: string): Promise<User | null> {
    return this.db.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first();
  }

  async create(input: UserInput): Promise<User> {
    await this.db.prepare(`INSERT INTO users (id, email) VALUES (?, ?)`).bind(input.id, input.email).run();
    return input;
  }
}

// Another implementation (in-memory, for tests)
class InMemoryUserRepository implements UserRepository {
  private users = new Map<string, User>();

  async getById(id: string): Promise<User | null> {
    return this.users.get(id) ?? null;
  }

  async create(input: UserInput): Promise<User> {
    this.users.set(input.id, input as User);
    return input as User;
  }
}
```

The service depends on the interface. The implementation is
swapped in tests.

## The pattern: test mocks

For Vitest, use `vi.fn()` to mock dependencies:
```ts
import { vi } from 'vitest';

test('getById returns the user', async () => {
  const mockDb = {
    prepare: vi.fn().mockReturnValue({
      bind: vi.fn().mockReturnValue({
        first: vi.fn().mockResolvedValue({ id: 'u_123', email: 'a@x.test' }),
      }),
    }),
  };
  const repo = new D1UserRepository(mockDb as any);
  const user = await repo.getById('u_123');
  expect(user).toEqual({ id: 'u_123', email: 'a@x.test' });
});
```

For complex mocks, use a mock factory:
```ts
function createMockD1(rows: any[] = []): D1Database {
  return {
    prepare: vi.fn().mockReturnValue({
      bind: vi.fn().mockReturnValue({
        first: vi.fn().mockResolvedValue(rows[0] ?? null),
        all: vi.fn().mockResolvedValue({ results: rows }),
        run: vi.fn().mockResolvedValue({ success: true }),
      }),
    }),
  } as any;
}
```

## The "DI container" alternative

For large apps, use a DI container (e.g. tsyringe,
InversifyJS). The container resolves dependencies automatically.

```ts
import { container } from 'tsyringe';

@injectable()
class UserService {
  constructor(@inject('D1') private db: D1Database) {}

  async getById(id: string): Promise<User> {
    return this.db.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first();
  }
}

// Wire up
container.register('D1', { useValue: env.DB! });
const userService = container.resolve(UserService);
```

For CF Workers, DI containers add cold-start overhead. Use
them only for complex apps.

## The "anti-patterns" of DI

### 1. Service locator
```ts
// ❌ Anti-pattern: service locator
async function getUser(id: string) {
  const db = getService('D1');  // Hidden dependency
  return db.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first();
}
```

Hidden dependencies are bad. Pass the dependency explicitly.

### 2. New'ing up in the function
```ts
// ❌ Anti-pattern
async function getUser(id: string) {
  const db = new D1Client();  // Can't mock
  return db.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first();
}
```

Always pass the dependency.

### 3. Static dependencies
```ts
// ❌ Anti-pattern
class UserService {
  async getById(id: string): Promise<User> {
    return globalDb.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first();
  }
}
```

Static state is hard to test and bug-prone.

## The "DI for CF Workers" tradeoffs

✅ **Testability:** Unit tests are fast (no real D1)
✅ **Flexibility:** Easy to swap implementations
❌ **Boilerplate:** More code (interfaces, constructors)
❌ **Cold start:** DI containers add overhead
❌ **Type complexity:** More types to maintain

For most CF Workers, **constructor injection + interface**
is enough. Use a DI container for complex apps.

## Verification
- **Test:** `test/user-service.test.ts > getById uses the
  injected DB, not env.DB` — passes
- **Coverage:** Unit tests cover 80%+ of the code
- **Audit:** Quarterly review of dependency wiring

## Gotchas
- **The dependency must be mockable.** If the type is
  `D1Database`, you need a way to mock it. Use an interface
  + impl pattern, or a mock factory.
- **The test mocks must be realistic.** A mock that returns
  the wrong shape will pass tests but fail in production.
- **The DI adds cold-start latency.** A complex DI container
  can add 50-100ms. For a hot path, use direct dependency
  injection (constructor params).
- **The "service" layer is often unnecessary.** A function
  that takes `env` and a `request` doesn't need a service.
  Add services only when the logic is complex.
- **DI is not a silver bullet.** Some dependencies (env
  bindings) can't be mocked. The trick is to identify which
  are testable and which aren't.

## Related
- `repository-pattern.md`
- `test-pyramid.md`
- `unit-testing-patterns.md` (later)
- Fowler DI: https://martinfowler.com/articles/injection.html
- tsyringe: https://github.com/microsoft/tsyringe

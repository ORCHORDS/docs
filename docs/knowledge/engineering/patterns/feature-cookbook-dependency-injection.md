# feature-cookbook-dependency-injection

**Issue:** DI — constructor injection, IoC, service locator
**Date:** 2026-08-09
**Status:** documented

## Symptom
You write a function. It uses `env.DB` directly. You
test it. The test needs a real DB. You mock the DB.
The mock is hard to maintain. The test breaks. You
wish you'd injected the DB.

## Root cause
**Hard-coded dependencies are hard to test.** Inject
them.

**Source:** Martin Fowler — Inversion of Control:
https://martinfowler.com/bliki/InversionOfControl.html

## The "DI" pattern

For DI, pass dependencies in:
```ts
// ❌ Bad: hard-coded
async function getUser(id: string) {
  return env.DB!.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first();
}

// ✅ Good: injected
async function getUser(id: string, db: D1Database) {
  return db.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first();
}
```

The dependency is a parameter.

## The "constructor injection" pattern

For class-based:
```ts
class UserService {
  constructor(private db: D1Database, private logger: Logger) {}

  async getUser(id: string): Promise<User | null> {
    this.logger.info({ msg: 'getUser', id });
    return this.db.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first();
  }
}

// In the worker
const userService = new UserService(env.DB!, logger);
```

The dependencies are constructor parameters.

## The "factory" pattern

For complex construction:
```ts
function createUserService(env: Env): UserService {
  const db = env.DB!;
  const logger = new Logger({ env: 'production' });
  return new UserService(db, logger);
}
```

The factory handles the construction.

## The "interface" pattern

For decoupling, use an interface:
```ts
interface UserRepository {
  getUser(id: string): Promise<User | null>;
  createUser(input: CreateUserInput): Promise<User>;
}

class D1UserRepository implements UserRepository {
  constructor(private db: D1Database) {}

  async getUser(id: string): Promise<User | null> {
    return this.db.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first() as Promise<User | null>;
  }

  async createUser(input: CreateUserInput): Promise<User> {
    const id = crypto.randomUUID();
    await this.db.prepare(`INSERT INTO users (id, email) VALUES (?, ?)`).bind(id, input.email).run();
    return { id, ...input };
  }
}

class InMemoryUserRepository implements UserRepository {
  private users = new Map<string, User>();

  async getUser(id: string): Promise<User | null> {
    return this.users.get(id) ?? null;
  }

  async createUser(input: CreateUserInput): Promise<User> {
    const id = crypto.randomUUID();
    const user = { id, ...input };
    this.users.set(id, user);
    return user;
  }
}
```

The interface allows swapping implementations.

## The "DI container" pattern

For a complex app, use a DI container:
```ts
const container = {
  db: env.DB!,
  logger: createLogger(env),
  userRepository: null as UserRepository | null,
  postRepository: null as PostRepository | null,
};

// Wire up
container.userRepository = new D1UserRepository(container.db);
container.postRepository = new D1PostRepository(container.db);
```

The container holds the wiring.

## The "service locator" pattern (anti-pattern)

For service locator, ask for dependencies:
```ts
// ❌ Anti-pattern
class UserService {
  async getUser(id: string): Promise<User | null> {
    const db = ServiceLocator.get<D1Database>('db');  // Hidden dependency
    return db.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first();
  }
}
```

Service locator hides dependencies; it's harder to test.

## The "Worker as DI" pattern

For CF Workers, the `env` is the DI:
```ts
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const userService = createUserService(env);
    return userService.getUser('u_1');
  },
};
```

The Worker creates the service with the env.

## The "DI in tests" pattern

For tests, inject mocks:
```ts
const mockDb = {
  prepare: vi.fn().mockReturnValue({
    bind: vi.fn().mockReturnValue({
      first: vi.fn().mockResolvedValue({ id: 'u_1', email: 'alice@example.com' }),
    }),
  }),
};

const userService = new UserService(mockDb as any, mockLogger);
const user = await userService.getUser('u_1');
expect(user).toEqual({ id: 'u_1', email: 'alice@example.com' });
```

The test injects mocks.

## The "DI benefits" pattern

For DI benefits:
- **Testable:** Inject mocks
- **Loose coupling:** Swap implementations
- **Flexibility:** Change deps without changing code
- **Readability:** Dependencies are explicit
- **Parallel development:** Multiple devs work on different
  impls

DI improves the code.

## The "DI anti-pattern" anti-patterns

### 1. Hard-coded deps
- **Issue:** Can't swap; can't test
- **Fix:** Inject

### 2. Service locator
- **Issue:** Hidden deps; hard to test
- **Fix:** Constructor injection

### 3. Too much DI
- **Issue:** Over-abstracted
- **Fix:** DI where it adds value

### 4. DI container overkill
- **Issue:** Complex setup for simple app
- **Fix:** Manual DI for small apps

### 5. No interface
- **Issue:** Tied to a specific implementation
- **Fix:** Use an interface

## Verification
- **Test:** Services are testable with mocks
- **Test:** Services can be swapped
- **Live:** Wiring is documented
- **Audit:** Quarterly DI review

## Gotchas
- **The "hard-coded deps" anti-pattern.** Inject.
- **The "service locator" anti-pattern.** Use constructor.
- **The "no interface" anti-pattern.** Use an interface.

## Related
- `dependency-injection.md`
- `repository-pattern.md`
- `feature-cookbook-testing-strategies.md`
- `feature-cookbook-feature-isolation.md`
- Martin Fowler: https://martinfowler.com/bliki/InversionOfControl.html
